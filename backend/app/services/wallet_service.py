import datetime as dt
import json
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.transaction import (
    IdempotencyKey,
    Transaction,
    TransactionEvent,
    TransactionStatus,
)
from app.models.wallet import LedgerEntry, Wallet
from app.services import audit_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_transaction, emit_to_user


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def get_wallet(db: Session, user_id: int) -> Wallet:
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).one_or_none()
    if not wallet:
        # Self-heal: provision a wallet if missing.
        wallet = Wallet(user_id=user_id, balance=0, currency="XAF")
        db.add(wallet)
        db.flush()
    return wallet


def apply_ledger(db: Session, wallet: Wallet, direction: str, amount: int,
                 transaction_id: int, description: str | None) -> int:
    """Adjust a wallet balance and record a ledger entry. Returns new balance."""
    if direction == "CREDIT":
        wallet.balance += amount
    elif direction == "DEBIT":
        wallet.balance -= amount
    else:  # pragma: no cover - guarded by callers
        raise ValueError(f"Unknown ledger direction: {direction}")
    db.add(
        LedgerEntry(
            wallet_id=wallet.id,
            transaction_id=transaction_id,
            direction=direction,
            amount=amount,
            balance_after=wallet.balance,
            description=description,
        )
    )
    return wallet.balance


def record_event(db: Session, txn: Transaction, event_type: str,
                 previous: str | None, new: str | None,
                 payload: dict | None = None) -> None:
    db.add(
        TransactionEvent(
            transaction_id=txn.id,
            event_type=event_type,
            previous_status=previous,
            new_status=new,
            payload=json.dumps(payload) if payload else None,
        )
    )


# Backwards-compatible private alias.
_record_event = record_event


def add_money(db: Session, user_id: int, amount: int, funding_method: str,
              idempotency_key: str | None) -> Transaction:
    """Credit the wallet through the transaction engine.

    Demonstrates the SRS money-movement pipeline:
    transaction -> ledger -> wallet -> transaction events -> notification -> Socket.IO.
    The database is the source of truth; sockets only deliver the result.
    """
    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")

    # Idempotency (SRS section 33).
    if idempotency_key:
        prior = (
            db.query(IdempotencyKey)
            .filter(
                IdempotencyKey.key == idempotency_key,
                IdempotencyKey.user_id == user_id,
            )
            .one_or_none()
        )
        if prior and prior.transaction_id:
            existing = db.get(Transaction, prior.transaction_id)
            if existing:
                return existing

    wallet = get_wallet(db, user_id)

    txn = Transaction(
        reference="txn_" + uuid.uuid4().hex[:16],
        user_id=user_id,
        type="ADD_MONEY",
        status=TransactionStatus.CREATED.value,
        amount=amount,
        fee=0,
        currency=wallet.currency,
        description=f"Add money via {funding_method}",
    )
    db.add(txn)
    db.flush()

    if idempotency_key:
        db.add(
            IdempotencyKey(key=idempotency_key, user_id=user_id, transaction_id=txn.id)
        )

    _record_event(db, txn, "TRANSACTION_CREATED", None, TransactionStatus.CREATED.value)

    # CREATED -> PENDING -> PROCESSING
    txn.status = TransactionStatus.PENDING.value
    _record_event(db, txn, "TRANSACTION_PENDING",
                  TransactionStatus.CREATED.value, TransactionStatus.PENDING.value)

    txn.status = TransactionStatus.PROCESSING.value
    _record_event(db, txn, "TRANSACTION_PROCESSING",
                  TransactionStatus.PENDING.value, TransactionStatus.PROCESSING.value)

    # Simulated provider success -> commit ledger + wallet.
    txn.provider_reference = "prov_" + uuid.uuid4().hex[:12]
    wallet.balance += amount
    db.add(
        LedgerEntry(
            wallet_id=wallet.id,
            transaction_id=txn.id,
            direction="CREDIT",
            amount=amount,
            balance_after=wallet.balance,
            description=txn.description,
        )
    )

    txn.status = TransactionStatus.SUCCESS.value
    txn.completed_at = _now()
    _record_event(db, txn, "TRANSACTION_SUCCESS",
                  TransactionStatus.PROCESSING.value, TransactionStatus.SUCCESS.value,
                  {"balance_after": wallet.balance})

    # Persist notifications BEFORE realtime delivery (source-of-truth rule).
    notification = create_notification(
        db,
        user_id=user_id,
        type="WALLET_CREDITED",
        title="Money Added",
        message=f"{amount / 100:,.2f} {wallet.currency} was added to your wallet.",
        priority="HIGH",
        data={"transaction_id": txn.id, "amount": amount},
    )

    audit_service.record(db, "TRANSACTION_CREATED", user_id=user_id, entity_type="transaction",
                         entity_id=txn.id,
                         meta={"type": txn.type, "amount": amount, "status": txn.status})

    # Commit the whole unit of work atomically.
    db.commit()
    db.refresh(txn)
    db.refresh(wallet)

    # Only now deliver realtime events.
    emit_to_user(user_id, "TRANSACTION_SUCCESS", {
        "transaction_id": txn.id,
        "reference": txn.reference,
        "status": txn.status,
        "amount": txn.amount,
        "currency": txn.currency,
    })
    emit_to_transaction(txn.id, "transaction:success", user_id, {
        "transaction_id": txn.id,
        "status": txn.status,
    })
    emit_to_user(user_id, "WALLET_BALANCE_UPDATED", {
        "balance": wallet.balance,
        "currency": wallet.currency,
    })
    deliver_notification(notification)

    return txn
