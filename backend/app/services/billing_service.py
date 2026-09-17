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
from app.services import (
    audit_service,
    catalog_service,
    fee_service,
    security_service,
    wallet_service,
)
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_transaction, emit_to_user

logger = get_logger("finpay.billing")

_DEMO_NAMES = [
    "JOHN DOE", "GRACE HOPPER", "ADA LOVELACE", "ALAN TURING",
    "MARIE CURIE", "KATHERINE JOHNSON", "LINUS PAULING", "NIKOLA TESLA",
]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _provider_list(db: Session, category: str, enabled_only: bool = True) -> list[dict]:
    return [
        {
            "id": p.provider_id,
            "name": p.name,
            "category": p.category,
            "flow": p.flow,
            "target_label": p.target_label,
            "icon": p.icon,
            "integration_mode": p.integration_mode,
            "fields": catalog_service.provider_public_fields(p),
        }
        for p in catalog_service.list_providers(db, category, enabled_only=enabled_only)
    ]


def list_category_providers(db: Session, category: str) -> list[dict]:
    """All enabled providers for a category (any flow) for the unified checkout."""
    return _provider_list(db, category, enabled_only=True)


def provider_name(db: Session, category: str, provider_id: str) -> str:
    p = catalog_service.get_provider(db, category, provider_id)
    return p.name if p else provider_id


def list_providers(db: Session, category: str) -> list[dict]:
    """Providers for validate_pay flows (e.g. electricity)."""
    rows = _provider_list(db, category)
    return [r for r in rows if r.get("flow") == "validate_pay"]


def list_topup_providers(db: Session, category: str) -> list[dict]:
    """Providers for direct_topup flows (airtime, data, water, custom)."""
    rows = _provider_list(db, category)
    return [r for r in rows if r.get("flow") == "direct_topup"]


def confirm_topup(db: Session, user: User, category: str, provider_id: str,
                  target: str, amount: int, pin: str,
                  idempotency_key: str | None,
                  message: str | None = None) -> Transaction:
    """Synchronous top-up for any direct_topup provider category.
    Targets ending in 0000 model a provider decline (no debit)."""
    category = catalog_service.normalize_category(category)
    provider = catalog_service.get_provider(db, category, provider_id)
    if not provider or not provider.enabled:
        raise ValidationError("Unknown provider.", code="UNKNOWN_PROVIDER")
    if provider.flow != "direct_topup":
        raise ValidationError(
            "This provider requires the validate-and-pay flow.",
            code="INVALID_PROVIDER_FLOW",
        )
    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")
    fee_service.ensure_enabled(db, category)
    if not user.transaction_pin_hash or not verify_password(pin, user.transaction_pin_hash):
        raise AuthError("Incorrect transaction PIN.", code="INVALID_PIN")

    if idempotency_key:
        prior = (
            db.query(IdempotencyKey)
            .filter(IdempotencyKey.key == idempotency_key,
                    IdempotencyKey.user_id == user.id)
            .one_or_none()
        )
        if prior and prior.transaction_id:
            existing = db.get(Transaction, prior.transaction_id)
            if existing:
                return existing

    fee = fee_service.compute_fee(db, category.upper(), amount)
    wallet = wallet_service.get_wallet(db, user.id)
    if wallet.balance < amount + fee:
        raise ValidationError("Insufficient wallet balance.", code="INSUFFICIENT_BALANCE")
    security_service.check_limits(db, user, amount)

    pname = provider.name
    note = (message or "").strip()
    description = f"{pname} {category} for {target}"
    if note:
        description = f"{description} — {note}"
    txn = Transaction(
        reference="txn_" + uuid.uuid4().hex[:16],
        user_id=user.id,
        type=category.upper(),
        status=TransactionStatus.CREATED.value,
        amount=amount,
        fee=0,
        currency=wallet.currency,
        description=description,
    )
    db.add(txn)
    db.flush()
    fee_service.attach_fee(db, txn, category.upper(), amount)
    if idempotency_key:
        db.add(IdempotencyKey(key=idempotency_key, user_id=user.id, transaction_id=txn.id))
    db.add(
        BillPayment(transaction_id=txn.id, user_id=user.id, category=category,
                    provider_id=provider_id, meter_number=target,
                    customer_name=target, amount=amount)
    )
    audit_service.record(db, "TRANSACTION_CREATED", user_id=user.id,
                         entity_type="transaction", entity_id=txn.id,
                         meta={"type": txn.type, "amount": amount, "fee": txn.fee})
    wallet_service.record_event(db, txn, "TRANSACTION_CREATED", None,
                                TransactionStatus.CREATED.value)
    txn.status = TransactionStatus.PROCESSING.value
    wallet_service.record_event(db, txn, "TRANSACTION_PROCESSING",
                                TransactionStatus.CREATED.value,
                                TransactionStatus.PROCESSING.value)

    # Simulated provider decline for targets ending 0000.
    if target.endswith("0000"):
        _fail(db, txn, user.id, "PROVIDER_DECLINED",
              "The provider declined the top-up.")
        return txn

    # Fee is already on the transaction; debit amount + fee now.
    txn.provider_reference = "prov_" + uuid.uuid4().hex[:12]
    balance = wallet_service.debit_with_fee(db, wallet, txn, txn.description)
    txn.status = TransactionStatus.SUCCESS.value
    txn.completed_at = _now()
    wallet_service.record_event(db, txn, "TRANSACTION_SUCCESS",
                                TransactionStatus.PROCESSING.value,
                                TransactionStatus.SUCCESS.value,
                                {"balance_after": balance})
    notif = create_notification(
        db, user_id=user.id, type="BILL_PAYMENT_SUCCESS", title="Top-up Successful",
        message=f"Your {category} top-up of {amount / 100:,.2f} {wallet.currency} was successful.",
        priority="HIGH",
        data={"transaction_id": txn.id, "amount": amount, "category": category},
    )
    from app.services import limit_service
    limit_service.record_debit_against_grant(db, user.id, amount)
    db.commit()
    db.refresh(txn)
    db.refresh(wallet)
    emit_to_user(user.id, "TRANSACTION_SUCCESS", {
        "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
        "amount": amount, "currency": wallet.currency,
    })
    emit_to_user(user.id, "WALLET_BALANCE_UPDATED",
                 {"balance": balance, "currency": wallet.currency})
    deliver_notification(notif)
    return txn


def _mock_customer_name(meter_number: str) -> str:
    digits = "".join(ch for ch in meter_number if ch.isdigit()) or "0"
    return _DEMO_NAMES[int(digits[-2:] or "0") % len(_DEMO_NAMES)]


def validate_meter(db: Session, user: User, provider_id: str,
                   meter_number: str) -> ElectricityValidation:
    return validate_account(db, user, "electricity", provider_id, meter_number)


def validate_account(
    db: Session,
    user: User,
    category: str,
    provider_id: str,
    phone: str,
) -> ElectricityValidation:
    """Validate destination for any validate_pay provider (phone maps to meter/account)."""
    category = catalog_service.normalize_category(category)
    provider = catalog_service.get_provider(db, category, provider_id)
    if not provider or not provider.enabled:
        raise ValidationError("Unknown provider.", code="UNKNOWN_PROVIDER")
    if provider.flow != "validate_pay":
        raise ValidationError(
            "This provider does not use validate-and-pay.",
            code="INVALID_PROVIDER_FLOW",
        )
    normalized = (phone or "").strip()
    if len(normalized) < 6:
        raise ValidationError(
            "Invalid account / phone. Enter at least 6 characters.",
            code="INVALID_METER",
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
                        pin: str, idempotency_key: str | None,
                        message: str | None = None,
                        category: str = "electricity") -> Transaction:
    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")

    category = catalog_service.normalize_category(category)
    fee_service.ensure_enabled(db, category)
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

    fee_op = category.upper()
    fee = fee_service.compute_fee(db, fee_op, amount)
    wallet = wallet_service.get_wallet(db, user.id)
    if wallet.balance < amount + fee:
        raise ValidationError("Insufficient wallet balance.", code="INSUFFICIENT_BALANCE")
    security_service.check_limits(db, user, amount)

    validation.consumed = True

    note = (message or "").strip()
    description = (
        f"{category_label_safe(category)} • "
        f"{provider_name(db, category, validation.provider_id)} • "
        f"{validation.meter_number}"
    )
    if note:
        description = f"{description} — {note}"

    txn = Transaction(
        reference="txn_" + uuid.uuid4().hex[:16],
        user_id=user.id,
        type=fee_op,
        status=TransactionStatus.CREATED.value,
        amount=amount,
        fee=0,
        currency=wallet.currency,
        description=description,
    )
    db.add(txn)
    db.flush()
    # Stamp fee onto the transaction before holding funds.
    fee_service.attach_fee(db, txn, fee_op, amount)

    db.add(
        BillPayment(
            transaction_id=txn.id,
            user_id=user.id,
            category=category,
            provider_id=validation.provider_id,
            meter_number=validation.meter_number,
            customer_name=validation.customer_name,
            amount=amount,
            token=validation.token,
        )
    )

    if idempotency_key:
        db.add(IdempotencyKey(key=idempotency_key, user_id=user.id, transaction_id=txn.id))

    audit_service.record(db, "TRANSACTION_CREATED", user_id=user.id,
                         entity_type="transaction", entity_id=txn.id,
                         meta={"type": fee_op, "amount": amount, "fee": txn.fee})

    wallet_service.record_event(db, txn, "TRANSACTION_CREATED", None,
                                TransactionStatus.CREATED.value)
    txn.status = TransactionStatus.PENDING.value
    wallet_service.record_event(db, txn, "TRANSACTION_PENDING",
                                TransactionStatus.CREATED.value,
                                TransactionStatus.PENDING.value)

    # Hold amount + fee immediately so the configured fee is locked before provider work.
    balance = wallet_service.debit_with_fee(db, wallet, txn, txn.description)

    # Simulated provider timeout: meters ending in 5555 or 4444 return an unknown
    # result. Per the SRS, we must NOT mark the transaction failed; leave it
    # pending for the reconciliation worker to settle (funds already held).
    if validation.meter_number.endswith(("5555", "4444")):
        txn.pending_reconciliation = True
        wallet_service.record_event(db, txn, "PROVIDER_TIMEOUT",
                                    TransactionStatus.PENDING.value,
                                    TransactionStatus.PENDING.value,
                                    {"held": wallet_service.total_charge(txn)})
        notif = create_notification(
            db, user_id=user.id, type="PAYMENT_PENDING", title="Payment Pending",
            message="Your payment is still being processed. We'll update you shortly.",
            priority="HIGH",
            data={"transaction_id": txn.id, "category": "electricity"},
        )
        db.commit()
        db.refresh(txn)
        emit_to_user(user.id, "TRANSACTION_PENDING", {
            "transaction_id": txn.id, "reference": txn.reference,
            "status": txn.status, "amount": txn.amount, "currency": txn.currency,
        })
        emit_to_user(user.id, "WALLET_BALANCE_UPDATED",
                     {"balance": balance, "currency": wallet.currency})
        deliver_notification(notif)
        return txn

    txn.status = TransactionStatus.PROCESSING.value
    wallet_service.record_event(db, txn, "TRANSACTION_PROCESSING",
                                TransactionStatus.PENDING.value,
                                TransactionStatus.PROCESSING.value,
                                {"held": wallet_service.total_charge(txn)})

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
    emit_to_user(user.id, "WALLET_BALANCE_UPDATED",
                 {"balance": balance, "currency": wallet.currency})

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
            # Funds (amount + fee) were already held at confirm time.
            if not wallet_service.has_debit_for_txn(db, txn.id):
                charge = wallet_service.total_charge(txn)
                if wallet.balance < charge:
                    _fail(db, txn, user_id, "INSUFFICIENT_BALANCE",
                          "Insufficient balance at settlement.")
                    return
                wallet_service.debit_with_fee(db, wallet, txn, txn.description)
            txn.provider_reference = "prov_" + uuid.uuid4().hex[:12]
            txn.status = TransactionStatus.SUCCESS.value
            txn.completed_at = _now()
            wallet_service.record_event(db, txn, "TRANSACTION_SUCCESS",
                                        TransactionStatus.PROCESSING.value,
                                        TransactionStatus.SUCCESS.value,
                                        {"balance_after": wallet.balance, "fee": txn.fee})
            notification = create_notification(
                db,
                user_id=user_id,
                type="BILL_PAYMENT_SUCCESS",
                title="Payment Successful",
                message=(
                    f"Your electricity payment of {txn.amount / 100:,.2f} {txn.currency} "
                    f"was successful (fee {txn.fee / 100:,.2f})."
                ),
                priority="HIGH",
                data={
                    "transaction_id": txn.id,
                    "amount": txn.amount,
                    "fee": txn.fee,
                    "category": "electricity",
                },
            )
            from app.services import limit_service
            limit_service.record_debit_against_grant(db, user_id, txn.amount)
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
    wallet = wallet_service.get_wallet(db, user_id)
    # Release any held amount + fee.
    if wallet_service.has_debit_for_txn(db, txn.id):
        balance = wallet_service.refund_charge(db, wallet, txn)
    else:
        balance = wallet.balance
    txn.status = TransactionStatus.FAILED.value
    txn.failure_reason = message
    txn.completed_at = _now()
    wallet_service.record_event(db, txn, "TRANSACTION_FAILED",
                                TransactionStatus.PROCESSING.value,
                                TransactionStatus.FAILED.value,
                                {"reason_code": reason_code, "refunded": True})
    notification = create_notification(
        db,
        user_id=user_id,
        type="BILL_PAYMENT_FAILED",
        title="Payment Failed",
        message=message,
        priority="HIGH",
        data={
            "transaction_id": txn.id,
            "reason_code": reason_code,
            "category": "electricity",
        },
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
    emit_to_user(user_id, "WALLET_BALANCE_UPDATED",
                 {"balance": balance, "currency": wallet.currency})
    deliver_notification(notification)


def category_label_safe(category: str) -> str:
    return catalog_service.category_label(category)


def _require_fields(provider, *, phone, amount, message) -> None:
    fields = catalog_service.provider_public_fields(provider)
    values = {"phone": phone, "amount": amount, "message": message}
    for field in fields:
        key = field["key"]
        enabled = field.get("enabled", True)
        required = field.get("required", False)
        val = values.get(key)
        if not enabled:
            if key == "phone" and val:
                raise ValidationError(
                    f"Field '{key}' is not enabled for this provider.",
                    code="FIELD_DISABLED",
                )
            if key == "amount" and val is not None:
                raise ValidationError(
                    f"Field '{key}' is not enabled for this provider.",
                    code="FIELD_DISABLED",
                )
            if key == "message" and val:
                raise ValidationError(
                    f"Field '{key}' is not enabled for this provider.",
                    code="FIELD_DISABLED",
                )
            continue
        if required:
            if key == "amount" and (val is None or int(val) <= 0):
                raise ValidationError("Amount is required.", code="FIELD_REQUIRED")
            if key in ("phone", "message") and not (val or "").strip():
                raise ValidationError(
                    f"{field.get('label') or key} is required.",
                    code="FIELD_REQUIRED",
                )


def pay(
    db: Session,
    user: User,
    *,
    category: str,
    provider_id: str,
    phone: str | None = None,
    amount: int | None = None,
    message: str | None = None,
    pin: str,
    validation_token: str | None = None,
    idempotency_key: str | None = None,
) -> Transaction:
    """Unified checkout: map phone/amount/message onto the provider flow."""
    category = catalog_service.normalize_category(category)
    provider = catalog_service.get_provider(db, category, provider_id)
    if not provider or not provider.enabled:
        raise ValidationError("Unknown provider.", code="UNKNOWN_PROVIDER")

    _require_fields(provider, phone=phone, amount=amount, message=message)

    if provider.flow == "direct_topup":
        return confirm_topup(
            db,
            user,
            category,
            provider_id,
            (phone or "").strip(),
            int(amount or 0),
            pin,
            idempotency_key,
            message=message,
        )

    if provider.flow == "validate_pay":
        if not validation_token:
            raise ValidationError(
                "Validate the account first.",
                code="VALIDATION_REQUIRED",
            )
        return confirm_electricity(
            db,
            user,
            validation_token=validation_token,
            amount=int(amount or 0),
            pin=pin,
            idempotency_key=idempotency_key,
            message=message,
            category=category,
        )

    raise ValidationError("Unsupported provider flow.", code="INVALID_PROVIDER_FLOW")
