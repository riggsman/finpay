import datetime as dt
import threading
import uuid

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthError, ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security import verify_password
from app.db.database import SessionLocal
from app.models.billing import BillPayment, ElectricityValidation
from app.models.transaction import (
    IdempotencyKey,
    Transaction,
    TransactionStatus,
)
from app.models.user import User
from app.models.wallet import LedgerEntry
from app.services import wallet_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_transaction, emit_to_user

logger = get_logger("finpay.billing")

# Static provider catalog for the MVP (backed by service_providers in later work).
ELECTRICITY_PROVIDERS = {
    "eneo": {"id": "eneo", "name": "ENEO", "category": "electricity"},
}

_DEMO_NAMES = [
    "JOHN DOE", "GRACE HOPPER", "ADA LOVELACE", "ALAN TURING",
    "MARIE CURIE", "KATHERINE JOHNSON", "LINUS PAULING", "NIKOLA TESLA",
]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def list_providers(category: str) -> list[dict]:
    if category != "electricity":
        return []
    return list(ELECTRICITY_PROVIDERS.values())


def _mock_customer_name(meter_number: str) -> str:
    digits = "".join(ch for ch in meter_number if ch.isdigit()) or "0"
    return _DEMO_NAMES[int(digits[-2:] or "0") % len(_DEMO_NAMES)]


def validate_meter(db: Session, user: User, provider_id: str,
                   meter_number: str) -> ElectricityValidation:
    if provider_id not in ELECTRICITY_PROVIDERS:
        raise ValidationError("Unknown electricity provider.", code="UNKNOWN_PROVIDER")
    normalized = meter_number.strip()
    if len(normalized) < 6 or not normalized.isdigit():
        raise ValidationError(
            "Invalid meter number. Enter at least 6 digits.", code="INVALID_METER"
        )

    validation = ElectricityValidation(
        token="val_" + uuid.uuid4().hex[:20],
        user_id=user.id,
        provider_id=provider_id,
        meter_number=normalized,
        customer_name=_mock_customer_name(normalized),
        expires_at=_now() + dt.timedelta(seconds=settings.VALIDATION_TOKEN_TTL_SECONDS),
    )
    db.add(validation)
    db.commit()
    db.refresh(validation)
    return validation


def confirm_electricity(db: Session, user: User, validation_token: str, amount: int,
                        pin: str, idempotency_key: str | None) -> Transaction:
    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")

    # Verify transaction PIN / authorization (SRS section 39).
    if not user.transaction_pin_hash or not verify_password(pin, user.transaction_pin_hash):
        raise AuthError("Incorrect transaction PIN.", code="INVALID_PIN")

    # Idempotency (SRS section 33).
    if idempotency_key:
        prior = (
            db.query(IdempotencyKey)
            .filter(
                IdempotencyKey.key == idempotency_key,
                IdempotencyKey.user_id == user.id,
            )
            .one_or_none()
        )
        if prior and prior.transaction_id:
            existing = db.get(Transaction, prior.transaction_id)
            if existing:
                return existing

    validation = (
        db.query(ElectricityValidation)
        .filter(ElectricityValidation.token == validation_token)
        .one_or_none()
    )
    if not validation or validation.user_id != user.id:
        raise NotFoundError("Validation not found.", code="VALIDATION_NOT_FOUND")
    if validation.consumed:
        raise ConflictError("This validation has already been used.",
                            code="VALIDATION_CONSUMED")
    if validation.expires_at < _now():
        raise ValidationError("Validation token expired. Please re-validate the meter.",
                              code="VALIDATION_EXPIRED")

    wallet = wallet_service.get_wallet(db, user.id)
    if wallet.balance < amount:
        raise ValidationError("Insufficient wallet balance.", code="INSUFFICIENT_BALANCE")

    validation.consumed = True

    txn = Transaction(
        reference="txn_" + uuid.uuid4().hex[:16],
        user_id=user.id,
        type="ELECTRICITY",
        status=TransactionStatus.CREATED.value,
        amount=amount,
        fee=0,
        currency=wallet.currency,
        description=f"Electricity • {ELECTRICITY_PROVIDERS[validation.provider_id]['name']} • {validation.meter_number}",
    )
    db.add(txn)
    db.flush()

    db.add(
        BillPayment(
            transaction_id=txn.id,
            user_id=user.id,
            category="electricity",
            provider_id=validation.provider_id,
            meter_number=validation.meter_number,
            customer_name=validation.customer_name,
            amount=amount,
            token=validation.token,
        )
    )

    if idempotency_key:
        db.add(IdempotencyKey(key=idempotency_key, user_id=user.id, transaction_id=txn.id))

    wallet_service.record_event(db, txn, "TRANSACTION_CREATED", None,
                                TransactionStatus.CREATED.value)
    txn.status = TransactionStatus.PENDING.value
    wallet_service.record_event(db, txn, "TRANSACTION_PENDING",
                                TransactionStatus.CREATED.value,
                                TransactionStatus.PENDING.value)
    txn.status = TransactionStatus.PROCESSING.value
    wallet_service.record_event(db, txn, "TRANSACTION_PROCESSING",
                                TransactionStatus.PENDING.value,
                                TransactionStatus.PROCESSING.value)

    db.commit()
    db.refresh(txn)

    # Emit the initial processing state to the transaction room and user room.
    emit_to_transaction(txn.id, "transaction:processing", user.id, {
        "transaction_id": txn.id,
        "status": txn.status,
    })
    emit_to_user(user.id, "TRANSACTION_PROCESSING", {
        "transaction_id": txn.id,
        "reference": txn.reference,
        "status": txn.status,
        "amount": txn.amount,
        "currency": txn.currency,
    })

    # Simulate an asynchronous provider response. The database remains the source
    # of truth; the socket only delivers the result once it is persisted.
    _schedule_provider_completion(txn.id, user.id, validation.meter_number)
    return txn


def _schedule_provider_completion(transaction_id: int, user_id: int,
                                  meter_number: str) -> None:
    delay = settings.PROVIDER_PROCESSING_DELAY_SECONDS
    timer = threading.Timer(
        delay, _complete_provider_operation, args=(transaction_id, user_id, meter_number)
    )
    timer.daemon = True
    timer.start()


def _complete_provider_operation(transaction_id: int, user_id: int,
                                 meter_number: str) -> None:
    """Runs in a background thread after the simulated provider delay."""
    db = SessionLocal()
    try:
        txn = db.get(Transaction, transaction_id)
        if not txn or txn.status != TransactionStatus.PROCESSING.value:
            return

        # Simulated provider outcome: meters ending in 9999 are declined.
        provider_success = not meter_number.endswith("9999")

        if provider_success:
            wallet = wallet_service.get_wallet(db, user_id)
            if wallet.balance < txn.amount:
                _fail(db, txn, user_id, "INSUFFICIENT_BALANCE",
                      "Insufficient balance at settlement.")
                return
            txn.provider_reference = "prov_" + uuid.uuid4().hex[:12]
            wallet.balance -= txn.amount
            db.add(
                LedgerEntry(
                    wallet_id=wallet.id,
                    transaction_id=txn.id,
                    direction="DEBIT",
                    amount=txn.amount,
                    balance_after=wallet.balance,
                    description=txn.description,
                )
            )
            txn.status = TransactionStatus.SUCCESS.value
            txn.completed_at = _now()
            wallet_service.record_event(db, txn, "TRANSACTION_SUCCESS",
                                        TransactionStatus.PROCESSING.value,
                                        TransactionStatus.SUCCESS.value,
                                        {"balance_after": wallet.balance})
            notification = create_notification(
                db,
                user_id=user_id,
                type="BILL_PAYMENT_SUCCESS",
                title="Payment Successful",
                message=f"Your electricity payment of {txn.amount / 100:,.2f} {txn.currency} was successful.",
                priority="HIGH",
                data={"transaction_id": txn.id, "amount": txn.amount},
            )
            db.commit()
            db.refresh(txn)
            db.refresh(wallet)

            emit_to_transaction(txn.id, "transaction:success", user_id, {
                "transaction_id": txn.id, "status": txn.status,
            })
            emit_to_user(user_id, "TRANSACTION_SUCCESS", {
                "transaction_id": txn.id, "reference": txn.reference,
                "status": txn.status, "amount": txn.amount, "currency": txn.currency,
            })
            emit_to_user(user_id, "WALLET_BALANCE_UPDATED", {
                "balance": wallet.balance, "currency": wallet.currency,
            })
            deliver_notification(notification)
        else:
            _fail(db, txn, user_id, "PROVIDER_DECLINED",
                  "The provider declined the transaction.")
    except Exception:  # pragma: no cover - defensive
        logger.exception("Provider completion failed for txn=%s", transaction_id)
        db.rollback()
    finally:
        db.close()


def _fail(db: Session, txn: Transaction, user_id: int, reason_code: str,
          message: str) -> None:
    txn.status = TransactionStatus.FAILED.value
    txn.failure_reason = message
    txn.completed_at = _now()
    wallet_service.record_event(db, txn, "TRANSACTION_FAILED",
                                TransactionStatus.PROCESSING.value,
                                TransactionStatus.FAILED.value,
                                {"reason_code": reason_code})
    notification = create_notification(
        db,
        user_id=user_id,
        type="BILL_PAYMENT_FAILED",
        title="Payment Failed",
        message=message,
        priority="HIGH",
        data={"transaction_id": txn.id, "reason_code": reason_code},
    )
    db.commit()
    db.refresh(txn)

    emit_to_transaction(txn.id, "transaction:failed", user_id, {
        "transaction_id": txn.id, "status": txn.status, "reason_code": reason_code,
    })
    emit_to_user(user_id, "TRANSACTION_FAILED", {
        "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
        "reason_code": reason_code, "retryable": True,
    })
    deliver_notification(notification)
