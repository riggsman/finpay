import datetime as dt
import json
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.transaction import (
    IdempotencyKey,
    Transaction,
    TransactionEvent,
    TransactionStatus,
)
from app.models.wallet import LedgerEntry, Wallet
from app.schemas import wallet as wallet_schemas
from app.schemas.wallet import (
    BankDepositDetails,
    CardDepositDetails,
    SendMoneyRequest,
    WithdrawRequest,
)
from app.services import audit_service, fee_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_transaction, emit_to_user

_CARD_METHODS = {"card", "bank card", "visa", "mastercard"}
_BANK_METHODS = {"bank", "bank transfer", "bank_transfer", "bic"}


def _mask_funding_details(
    method: str,
    card_details: CardDepositDetails | None,
    bank_details: BankDepositDetails | None,
) -> str | None:
    """Return a safe identifier snippet for transaction descriptions (no secrets)."""
    method = (method or "").strip().lower()
    if method in _CARD_METHODS and card_details is not None:
        digits = "".join(ch for ch in (card_details.card_number or "") if ch.isdigit())
        last4 = digits[-4:] if len(digits) >= 4 else "****"
        return f"card ****{last4}"
    if method in _BANK_METHODS and bank_details is not None:
        acct = "".join(ch for ch in (bank_details.account_number or "") if ch.isalnum())
        tail = acct[-4:] if len(acct) >= 4 else "****"
        code = (bank_details.bank_code or "").strip() or "bank"
        return f"{code} ****{tail}"
    return None


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
    if amount < 0:
        raise ValidationError("Ledger amount cannot be negative.", code="INVALID_AMOUNT")
    if direction == "CREDIT":
        wallet.balance += amount
    elif direction == "DEBIT":
        if wallet.balance < amount:
            raise ValidationError("Insufficient wallet balance.", code="INSUFFICIENT_BALANCE")
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
    db.flush()
    return wallet.balance


def total_charge(txn: Transaction) -> int:
    """Amount the payer owes: principal + service fee."""
    return int(txn.amount) + int(txn.fee or 0)


def debit_with_fee(db: Session, wallet: Wallet, txn: Transaction,
                   description: str | None = None) -> int:
    """Debit ``amount + fee`` for an outbound transaction. Fee must already be set."""
    charge = total_charge(txn)
    if charge <= 0:
        raise ValidationError("Charge must be positive.", code="INVALID_AMOUNT")
    return apply_ledger(
        db, wallet, "DEBIT", charge, txn.id, description or txn.description
    )


def credit_net_of_fee(db: Session, wallet: Wallet, txn: Transaction,
                      description: str | None = None) -> int:
    """Credit deposit principal minus fee. Fee must already be set on ``txn``."""
    fee = int(txn.fee or 0)
    if fee >= int(txn.amount):
        raise ValidationError("Fee exceeds deposit amount.", code="FEE_EXCEEDS_AMOUNT")
    credited = int(txn.amount) - fee
    return apply_ledger(
        db, wallet, "CREDIT", credited, txn.id, description or txn.description
    )


def refund_charge(db: Session, wallet: Wallet, txn: Transaction,
                  description: str | None = None) -> int:
    """Credit back a previously held ``amount + fee`` (failed provider settlement)."""
    charge = total_charge(txn)
    if charge <= 0:
        return wallet.balance
    return apply_ledger(
        db,
        wallet,
        "CREDIT",
        charge,
        txn.id,
        description or f"Refund · {txn.description or txn.type}",
    )


def has_debit_for_txn(db: Session, transaction_id: int) -> bool:
    return (
        db.query(LedgerEntry)
        .filter(
            LedgerEntry.transaction_id == transaction_id,
            LedgerEntry.direction == "DEBIT",
        )
        .first()
        is not None
    )

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


def _use_campay_for_deposit(funding_method: str) -> bool:
    from app.integrations.campay import campay_configured

    return campay_configured() and (funding_method or "").strip().lower() in {
        "mobile_money",
        "momo",
        "mtn",
        "orange",
    }


def settle_campay_deposit_success(db: Session, txn: Transaction) -> Transaction:
    """Credit wallet for a Campay collection that completed successfully."""
    if txn.type != "ADD_MONEY":
        raise ValidationError("Not a deposit transaction.", code="INVALID_TYPE")
    if txn.status == TransactionStatus.SUCCESS.value:
        return txn
    if txn.status not in (
        TransactionStatus.CREATED.value,
        TransactionStatus.PENDING.value,
        TransactionStatus.PROCESSING.value,
    ):
        raise ValidationError("Deposit cannot be settled in this state.", code="INVALID_STATUS")

    wallet = get_wallet(db, txn.user_id)
    # Avoid double-credit.
    existing_credit = (
        db.query(LedgerEntry)
        .filter(
            LedgerEntry.transaction_id == txn.id,
            LedgerEntry.direction == "CREDIT",
        )
        .first()
    )
    if existing_credit:
        balance = wallet.balance
    else:
        balance = credit_net_of_fee(db, wallet, txn)

    prev = txn.status
    txn.status = TransactionStatus.SUCCESS.value
    txn.completed_at = _now()
    txn.pending_reconciliation = False
    fee = int(txn.fee or 0)
    record_event(
        db,
        txn,
        "TRANSACTION_SUCCESS",
        prev,
        TransactionStatus.SUCCESS.value,
        {
            "balance_after": balance,
            "fee": fee,
            "credited": int(txn.amount) - fee,
            "provider": "campay",
        },
    )
    notification = create_notification(
        db,
        user_id=txn.user_id,
        type="WALLET_CREDITED",
        title="Money Added",
        message=(
            f"{txn.amount / 100:,.2f} {txn.currency} mobile money deposit received "
            f"(fee {fee / 100:,.2f}; credited {(txn.amount - fee) / 100:,.2f})."
        ),
        priority="HIGH",
        data={"transaction_id": txn.id, "amount": txn.amount, "fee": fee},
    )
    db.commit()
    db.refresh(txn)
    db.refresh(wallet)
    emit_to_user(txn.user_id, "TRANSACTION_SUCCESS", {
        "transaction_id": txn.id,
        "reference": txn.reference,
        "status": txn.status,
        "amount": txn.amount,
        "fee": txn.fee,
        "currency": txn.currency,
    })
    emit_to_transaction(txn.id, "transaction:success", txn.user_id, {
        "transaction_id": txn.id,
        "status": txn.status,
    })
    emit_to_user(txn.user_id, "WALLET_BALANCE_UPDATED", {
        "balance": wallet.balance,
        "currency": wallet.currency,
    })
    deliver_notification(notification)
    return txn


def settle_campay_deposit_failed(db: Session, txn: Transaction, reason: str) -> Transaction:
    if txn.type != "ADD_MONEY":
        raise ValidationError("Not a deposit transaction.", code="INVALID_TYPE")
    if txn.status == TransactionStatus.FAILED.value:
        return txn
    if txn.status == TransactionStatus.SUCCESS.value:
        return txn

    prev = txn.status
    txn.status = TransactionStatus.FAILED.value
    txn.failure_reason = (reason or "Mobile money payment failed.")[:255]
    txn.completed_at = _now()
    txn.pending_reconciliation = False
    record_event(
        db,
        txn,
        "TRANSACTION_FAILED",
        prev,
        TransactionStatus.FAILED.value,
        {"provider": "campay", "reason": txn.failure_reason},
    )
    notification = create_notification(
        db,
        user_id=txn.user_id,
        type="WALLET_DEPOSIT_FAILED",
        title="Deposit Failed",
        message=txn.failure_reason or "Your mobile money deposit could not be completed.",
        priority="HIGH",
        data={"transaction_id": txn.id, "amount": txn.amount},
    )
    db.commit()
    db.refresh(txn)
    emit_to_user(txn.user_id, "TRANSACTION_FAILED", {
        "transaction_id": txn.id,
        "reference": txn.reference,
        "status": txn.status,
        "reason_code": "PROVIDER_FAILED",
        "retryable": True,
    })
    emit_to_transaction(txn.id, "transaction:failed", txn.user_id, {
        "transaction_id": txn.id,
        "status": txn.status,
    })
    deliver_notification(notification)
    return txn


def add_money(
    db: Session,
    user_id: int,
    amount: int,
    funding_method: str,
    idempotency_key: str | None,
    phone: str | None = None,
    card_details: CardDepositDetails | None = None,
    bank_details: BankDepositDetails | None = None,
) -> Transaction:
    """Credit the wallet through the transaction engine.

    Mobile money with Campay credentials initiates a collection and leaves the
    transaction PENDING until Campay confirms (reconcile/webhook). Other
    funding methods keep the instant mock credit path.
    """
    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")
    fee_service.ensure_enabled(db, "add_money")
    method = (funding_method or "card").strip().lower() or "card"

    if method in _CARD_METHODS:
        fee_service.ensure_enabled(db, "funding_card")
        if card_details is None:
            raise ValidationError(
                "card_details is required for card deposits.",
                code="CARD_DETAILS_REQUIRED",
            )
    elif method in _BANK_METHODS:
        fee_service.ensure_enabled(db, "funding_bank")
        if bank_details is None:
            raise ValidationError(
                "bank_details is required for bank deposits.",
                code="BANK_DETAILS_REQUIRED",
            )
    elif method in {"mobile_money", "momo", "mtn", "orange"}:
        fee_service.ensure_enabled(db, "funding_mobile_money")
    else:
        raise ValidationError(
            "Unsupported funding method. Use card, bank, or mobile_money.",
            code="INVALID_FUNDING_METHOD",
        )

    # Never store plaintext PAN or CVV. Mask card/bank identifiers before
    # persisting them on the transaction description.
    masked_holder_id = _mask_funding_details(method, card_details, bank_details)
    effective_phone = phone
    if method in {"mobile_money", "momo", "mtn", "orange"} and not effective_phone:
        raise ValidationError("phone is required for mobile money deposits.", code="PHONE_REQUIRED")

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
    use_campay = _use_campay_for_deposit(method)

    desc = f"Add money via {method}"
    if masked_holder_id:
        desc = f"Add money via {masked_holder_id}"

    txn = Transaction(
        reference="txn_" + uuid.uuid4().hex[:16],
        user_id=user_id,
        type="ADD_MONEY",
        status=TransactionStatus.CREATED.value,
        amount=amount,
        fee=0,
        currency=wallet.currency,
        description=desc,
    )
    db.add(txn)
    db.flush()

    fee = fee_service.attach_fee(db, txn, "DEPOSIT", amount)
    if fee >= amount:
        raise ValidationError("Fee exceeds deposit amount.", code="FEE_EXCEEDS_AMOUNT")

    if idempotency_key:
        db.add(
            IdempotencyKey(key=idempotency_key, user_id=user_id, transaction_id=txn.id)
        )

    _record_event(db, txn, "TRANSACTION_CREATED", None, TransactionStatus.CREATED.value)

    txn.status = TransactionStatus.PENDING.value
    _record_event(
        db,
        txn,
        "TRANSACTION_PENDING",
        TransactionStatus.CREATED.value,
        TransactionStatus.PENDING.value,
    )

    if use_campay:
        from app.integrations.campay import (
            get_campay_client,
            minor_to_campay_amount,
            normalize_msisdn,
        )

        msisdn = normalize_msisdn(phone)
        amount_xaf = minor_to_campay_amount(amount)
        txn.description = f"Add money via mobile money ({msisdn})"
        txn.status = TransactionStatus.PROCESSING.value
        _record_event(
            db,
            txn,
            "TRANSACTION_PROCESSING",
            TransactionStatus.PENDING.value,
            TransactionStatus.PROCESSING.value,
            {"provider": "campay", "phone": msisdn},
        )
        # Flush before external call so external_reference is durable if Campay
        # accepts but we crash before commit.
        db.flush()
        try:
            result = get_campay_client().collect(
                amount_xaf=amount_xaf,
                phone=msisdn,
                description=txn.description,
                external_reference=txn.reference,
            )
        except Exception as exc:
            txn.status = TransactionStatus.FAILED.value
            txn.failure_reason = str(getattr(exc, "message", None) or exc)[:255]
            txn.completed_at = _now()
            _record_event(
                db,
                txn,
                "TRANSACTION_FAILED",
                TransactionStatus.PROCESSING.value,
                TransactionStatus.FAILED.value,
                {"provider": "campay", "error": txn.failure_reason},
            )
            audit_service.record(
                db,
                "TRANSACTION_CREATED",
                user_id=user_id,
                entity_type="transaction",
                entity_id=txn.id,
                meta={"type": txn.type, "amount": amount, "fee": fee, "status": txn.status},
            )
            db.commit()
            db.refresh(txn)
            raise

        campay_ref = str(result.get("reference") or "").strip()
        if not campay_ref:
            txn.status = TransactionStatus.FAILED.value
            txn.failure_reason = "Campay did not return a transaction reference."
            txn.completed_at = _now()
            _record_event(
                db,
                txn,
                "TRANSACTION_FAILED",
                TransactionStatus.PROCESSING.value,
                TransactionStatus.FAILED.value,
                {"provider": "campay"},
            )
            db.commit()
            db.refresh(txn)
            raise ValidationError(txn.failure_reason, code="CAMPAY_ERROR")

        txn.provider_reference = campay_ref
        txn.status = TransactionStatus.PENDING.value
        txn.pending_reconciliation = True
        from app.services import campay_payment_service

        campay_payment_service.record_initiate(
            db,
            reference=campay_ref,
            endpoint="collect",
            user_id=user_id,
            transaction_id=txn.id,
            external_reference=txn.reference,
            phone_number=msisdn,
            amount_minor=amount,
            currency=wallet.currency,
            operator=result.get("operator"),
            raw=result,
        )
        campay_payment_service.apply_status_payload(
            db, result, transaction=txn, endpoint="collect", notify=False
        )
        _record_event(
            db,
            txn,
            "TRANSACTION_PENDING",
            TransactionStatus.PROCESSING.value,
            TransactionStatus.PENDING.value,
            {
                "provider": "campay",
                "campay_reference": campay_ref,
                "ussd_code": result.get("ussd_code"),
                "operator": result.get("operator"),
            },
        )
        audit_service.record(
            db,
            "TRANSACTION_CREATED",
            user_id=user_id,
            entity_type="transaction",
            entity_id=txn.id,
            meta={
                "type": txn.type,
                "amount": amount,
                "fee": fee,
                "status": txn.status,
                "provider": "campay",
                "campay_reference": campay_ref,
            },
        )
        db.commit()
        db.refresh(txn)
        emit_to_user(user_id, "TRANSACTION_PENDING", {
            "transaction_id": txn.id,
            "reference": txn.reference,
            "status": txn.status,
            "amount": txn.amount,
            "currency": txn.currency,
            "provider_reference": txn.provider_reference,
        })
        return txn

    # --- Mock / non-Campay funding methods (instant credit) ---
    txn.status = TransactionStatus.PROCESSING.value
    _record_event(
        db,
        txn,
        "TRANSACTION_PROCESSING",
        TransactionStatus.PENDING.value,
        TransactionStatus.PROCESSING.value,
    )

    txn.provider_reference = "prov_" + uuid.uuid4().hex[:12]
    balance = credit_net_of_fee(db, wallet, txn)

    txn.status = TransactionStatus.SUCCESS.value
    txn.completed_at = _now()
    _record_event(
        db,
        txn,
        "TRANSACTION_SUCCESS",
        TransactionStatus.PROCESSING.value,
        TransactionStatus.SUCCESS.value,
        {"balance_after": balance, "fee": fee, "credited": amount - fee},
    )

    notification = create_notification(
        db,
        user_id=user_id,
        type="WALLET_CREDITED",
        title="Money Added",
        message=(
            f"{amount / 100:,.2f} {wallet.currency} deposit received "
            f"(fee {fee / 100:,.2f}; credited {(amount - fee) / 100:,.2f})."
        ),
        priority="HIGH",
        data={"transaction_id": txn.id, "amount": amount, "fee": fee},
    )

    audit_service.record(
        db,
        "TRANSACTION_CREATED",
        user_id=user_id,
        entity_type="transaction",
        entity_id=txn.id,
        meta={"type": txn.type, "amount": amount, "fee": fee, "status": txn.status},
    )

    db.commit()
    db.refresh(txn)
    db.refresh(wallet)

    emit_to_user(user_id, "TRANSACTION_SUCCESS", {
        "transaction_id": txn.id,
        "reference": txn.reference,
        "status": txn.status,
        "amount": txn.amount,
        "fee": txn.fee,
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
