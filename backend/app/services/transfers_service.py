import datetime as dt
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, NotFoundError, ValidationError
from app.core.security import verify_password
from app.models.transaction import IdempotencyKey, Transaction, TransactionStatus
from app.models.user import User, UserStatus
from app.services import audit_service, fee_service, security_service, wallet_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_user

# Realtime delivery context for send_money when commit is deferred (money-request pay).
_SEND_MONEY_RT: dict[int, dict] = {}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _check_pin(user: User, pin: str) -> None:
    if not user.transaction_pin_hash or not verify_password(pin, user.transaction_pin_hash):
        raise AuthError("Incorrect transaction PIN.", code="INVALID_PIN")


def _idempotent_hit(db: Session, user_id: int, key: str | None) -> Transaction | None:
    if not key:
        return None
    prior = (
        db.query(IdempotencyKey)
        .filter(IdempotencyKey.key == key, IdempotencyKey.user_id == user_id)
        .one_or_none()
    )
    if prior and prior.transaction_id:
        return db.get(Transaction, prior.transaction_id)
    return None


def _new_txn(user_id: int, type_: str, amount: int, currency: str,
             description: str) -> Transaction:
    return Transaction(
        reference="txn_" + uuid.uuid4().hex[:16],
        user_id=user_id,
        type=type_,
        status=TransactionStatus.CREATED.value,
        amount=amount,
        fee=0,
        currency=currency,
        description=description,
    )


def send_money(
    db: Session,
    sender: User,
    recipient_identifier: str,
    amount: int,
    pin: str,
    idempotency_key: str | None,
    *,
    commit: bool = True,
) -> Transaction:
    """Transfer wallet funds between two users.

    When ``commit=False`` the ledger rows and notifications are flushed but not
    committed or delivered — callers (e.g. money-request pay) can include extra
    row updates in the same transaction, then call
    ``publish_send_money_realtime`` after their own commit.
    """
    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")
    fee_service.ensure_enabled(db, "send_money")
    _check_pin(sender, pin)

    hit = _idempotent_hit(db, sender.id, idempotency_key)
    if hit:
        return hit

    recipient = (
        db.query(User)
        .filter(or_(User.phone == recipient_identifier, User.email == recipient_identifier))
        .one_or_none()
    )
    if not recipient or recipient.status != UserStatus.ACTIVE:
        raise NotFoundError("Recipient not found.", code="RECIPIENT_NOT_FOUND")
    if recipient.id == sender.id:
        raise ValidationError("You cannot send money to yourself.", code="SELF_TRANSFER")

    fee = fee_service.compute_fee(db, "SEND_MONEY", amount)
    sender_wallet = wallet_service.get_wallet(db, sender.id)
    if sender_wallet.balance < amount + fee:
        raise ValidationError("Insufficient wallet balance.", code="INSUFFICIENT_BALANCE")
    security_service.check_limits(db, sender, amount)
    recipient_wallet = wallet_service.get_wallet(db, recipient.id)

    sender_name = sender.full_name or sender.phone
    recipient_name = recipient.full_name or recipient.phone

    # Sender (debit) transaction — attach fee before any debit.
    sender_txn = _new_txn(sender.id, "SEND_MONEY", amount, sender_wallet.currency,
                          f"Transfer to {recipient_name}")
    db.add(sender_txn)
    db.flush()
    fee_service.attach_fee(db, sender_txn, "SEND_MONEY", amount)
    if idempotency_key:
        db.add(IdempotencyKey(key=idempotency_key, user_id=sender.id,
                              transaction_id=sender_txn.id))

    # Recipient (credit) transaction.
    recipient_txn = _new_txn(recipient.id, "TRANSFER_RECEIVED", amount,
                             recipient_wallet.currency, f"Transfer from {sender_name}")
    db.add(recipient_txn)
    db.flush()

    for txn in (sender_txn, recipient_txn):
        wallet_service.record_event(db, txn, "TRANSACTION_CREATED", None,
                                    TransactionStatus.CREATED.value)

    sender_balance = wallet_service.debit_with_fee(
        db, sender_wallet, sender_txn, sender_txn.description
    )
    recipient_balance = wallet_service.apply_ledger(
        db, recipient_wallet, "CREDIT", amount, recipient_txn.id, recipient_txn.description
    )

    for txn in (sender_txn, recipient_txn):
        txn.status = TransactionStatus.SUCCESS.value
        txn.completed_at = _now()
        txn.provider_reference = "int_" + uuid.uuid4().hex[:12]
        wallet_service.record_event(db, txn, "TRANSACTION_SUCCESS",
                                    TransactionStatus.CREATED.value,
                                    TransactionStatus.SUCCESS.value)

    sender_notif = create_notification(
        db, user_id=sender.id, type="TRANSFER_SENT", title="Transfer Sent",
        message=f"You sent {amount / 100:,.2f} {sender_wallet.currency} to {recipient_name}.",
        priority="HIGH", data={"transaction_id": sender_txn.id, "amount": amount},
    )
    recipient_notif = create_notification(
        db, user_id=recipient.id, type="TRANSFER_RECEIVED", title="Money Received",
        message=f"You received {amount / 100:,.2f} {recipient_wallet.currency} from {sender_name}.",
        priority="HIGH", data={"transaction_id": recipient_txn.id, "amount": amount},
    )

    audit_service.record(db, "TRANSACTION_CREATED", user_id=sender.id,
                         entity_type="transaction", entity_id=sender_txn.id,
                         meta={"type": "SEND_MONEY", "amount": amount, "status": "SUCCESS"})
    from app.services import limit_service
    limit_service.record_debit_against_grant(db, sender.id, amount)

    # Stash delivery context for publish_send_money_realtime (survives expire_on_commit).
    _SEND_MONEY_RT[sender_txn.id] = {
        "recipient_id": recipient.id,
        "recipient_txn_id": recipient_txn.id,
        "amount": amount,
        "sender_name": sender_name,
        "recipient_name": recipient_name,
        "sender_balance": sender_balance,
        "recipient_balance": recipient_balance,
        "sender_currency": sender_wallet.currency,
        "recipient_currency": recipient_wallet.currency,
        "sender_notif_id": sender_notif.id,
        "recipient_notif_id": recipient_notif.id,
    }

    if commit:
        db.commit()
        db.refresh(sender_txn)
        publish_send_money_realtime(db, sender_txn)

    return sender_txn


def publish_send_money_realtime(db: Session, sender_txn: Transaction) -> None:
    """Emit Socket.IO / push / email for a committed P2P transfer."""
    ctx = _SEND_MONEY_RT.pop(sender_txn.id, {}) or {}
    recipient_id = ctx.get("recipient_id")
    amount = int(ctx.get("amount") or sender_txn.amount)
    sender_name = ctx.get("sender_name") or "FinPay user"
    recipient_name = ctx.get("recipient_name") or "FinPay user"
    sender_balance = ctx.get("sender_balance")
    recipient_balance = ctx.get("recipient_balance")
    sender_currency = ctx.get("sender_currency") or sender_txn.currency
    recipient_currency = ctx.get("recipient_currency") or sender_txn.currency

    if sender_balance is None:
        sender_balance = wallet_service.get_wallet(db, sender_txn.user_id).balance
    if recipient_id is not None and recipient_balance is None:
        recipient_balance = wallet_service.get_wallet(db, recipient_id).balance

    from app.models.notification import Notification

    sender_notif = None
    recipient_notif = None
    if ctx.get("sender_notif_id"):
        sender_notif = db.get(Notification, ctx["sender_notif_id"])
    if ctx.get("recipient_notif_id"):
        recipient_notif = db.get(Notification, ctx["recipient_notif_id"])

    # Realtime: sender side.
    emit_to_user(sender_txn.user_id, "TRANSFER_SENT", {
        "transaction_id": sender_txn.id, "amount": amount, "to": recipient_name,
    })
    emit_to_user(sender_txn.user_id, "TRANSACTION_SUCCESS", {
        "transaction_id": sender_txn.id, "reference": sender_txn.reference,
        "status": sender_txn.status, "amount": amount, "currency": sender_currency,
    })
    emit_to_user(sender_txn.user_id, "WALLET_BALANCE_UPDATED", {
        "balance": sender_balance, "currency": sender_currency,
    })
    if sender_notif:
        deliver_notification(sender_notif)

    # Realtime: recipient side.
    if recipient_id is not None:
        emit_to_user(recipient_id, "TRANSFER_RECEIVED", {
            "transaction_id": ctx.get("recipient_txn_id"),
            "amount": amount,
            "from": sender_name,
        })
        emit_to_user(recipient_id, "WALLET_BALANCE_UPDATED", {
            "balance": recipient_balance, "currency": recipient_currency,
        })
        if recipient_notif:
            deliver_notification(recipient_notif)


def settle_campay_withdraw_success(db: Session, txn: Transaction) -> Transaction:
    """Finalize a Campay withdrawal after SUCCESSFUL provider status."""
    if txn.type != "WITHDRAW":
        raise ValidationError("Not a withdrawal transaction.", code="INVALID_TYPE")
    if txn.status == TransactionStatus.SUCCESS.value:
        return txn

    wallet = wallet_service.get_wallet(db, txn.user_id)
    prev = txn.status
    txn.status = TransactionStatus.SUCCESS.value
    txn.completed_at = _now()
    txn.pending_reconciliation = False
    wallet_service.record_event(
        db,
        txn,
        "TRANSACTION_SUCCESS",
        prev,
        TransactionStatus.SUCCESS.value,
        {"provider": "campay", "balance_after": wallet.balance},
    )
    notif = create_notification(
        db,
        user_id=txn.user_id,
        type="WALLET_DEBITED",
        title="Withdrawal Successful",
        message=f"You withdrew {txn.amount / 100:,.2f} {txn.currency}.",
        priority="HIGH",
        data={"transaction_id": txn.id, "amount": txn.amount},
    )
    from app.services import limit_service

    limit_service.record_debit_against_grant(db, txn.user_id, txn.amount)
    db.commit()
    db.refresh(txn)
    db.refresh(wallet)
    emit_to_user(txn.user_id, "WALLET_DEBITED", {"transaction_id": txn.id, "amount": txn.amount})
    emit_to_user(txn.user_id, "TRANSACTION_SUCCESS", {
        "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
        "amount": txn.amount, "currency": txn.currency,
    })
    emit_to_user(txn.user_id, "WALLET_BALANCE_UPDATED", {
        "balance": wallet.balance, "currency": wallet.currency,
    })
    deliver_notification(notif)
    return txn


def settle_campay_withdraw_failed(db: Session, txn: Transaction, reason: str) -> Transaction:
    """Refund held debit when Campay withdrawal fails."""
    if txn.type != "WITHDRAW":
        raise ValidationError("Not a withdrawal transaction.", code="INVALID_TYPE")
    if txn.status == TransactionStatus.FAILED.value:
        return txn
    if txn.status == TransactionStatus.SUCCESS.value:
        return txn

    wallet = wallet_service.get_wallet(db, txn.user_id)
    if wallet_service.has_debit_for_txn(db, txn.id):
        balance = wallet_service.refund_charge(db, wallet, txn, f"Refund · {txn.description}")
    else:
        balance = wallet.balance
    prev = txn.status
    txn.status = TransactionStatus.FAILED.value
    txn.failure_reason = (reason or "Withdrawal failed at provider.")[:255]
    txn.completed_at = _now()
    txn.pending_reconciliation = False
    wallet_service.record_event(
        db,
        txn,
        "TRANSACTION_FAILED",
        prev,
        TransactionStatus.FAILED.value,
        {"provider": "campay", "refunded": True, "balance_after": balance},
    )
    notif = create_notification(
        db,
        user_id=txn.user_id,
        type="WALLET_WITHDRAW_FAILED",
        title="Withdrawal Failed",
        message=txn.failure_reason or "Your withdrawal could not be completed. Funds were returned.",
        priority="HIGH",
        data={"transaction_id": txn.id, "amount": txn.amount},
    )
    db.commit()
    db.refresh(txn)
    emit_to_user(txn.user_id, "TRANSACTION_FAILED", {
        "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
        "reason_code": "PROVIDER_FAILED", "retryable": True,
    })
    emit_to_user(txn.user_id, "WALLET_BALANCE_UPDATED", {
        "balance": balance, "currency": wallet.currency,
    })
    deliver_notification(notif)
    return txn


def withdraw(db: Session, user: User, amount: int, destination: str, pin: str,
             idempotency_key: str | None) -> Transaction:
    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")
    fee_service.ensure_enabled(db, "withdraw")
    _check_pin(user, pin)

    hit = _idempotent_hit(db, user.id, idempotency_key)
    if hit:
        return hit

    from app.integrations.campay import (
        campay_configured,
        get_campay_client,
        map_campay_status,
        minor_to_campay_amount,
        normalize_msisdn,
    )

    use_campay = campay_configured()
    fee = fee_service.compute_fee(db, "WITHDRAW", amount)
    wallet = wallet_service.get_wallet(db, user.id)
    if wallet.balance < amount + fee:
        raise ValidationError("Insufficient wallet balance.", code="INSUFFICIENT_BALANCE")
    security_service.check_limits(db, user, amount)

    dest_label = (destination or "").strip()
    if use_campay:
        msisdn = normalize_msisdn(dest_label)
        dest_label = msisdn
        amount_xaf = minor_to_campay_amount(amount)
    else:
        msisdn = None
        amount_xaf = None

    txn = _new_txn(user.id, "WITHDRAW", amount, wallet.currency,
                   f"Withdrawal to {dest_label}")
    db.add(txn)
    db.flush()
    fee_service.attach_fee(db, txn, "WITHDRAW", amount)
    if idempotency_key:
        db.add(IdempotencyKey(key=idempotency_key, user_id=user.id, transaction_id=txn.id))

    wallet_service.record_event(db, txn, "TRANSACTION_CREATED", None,
                                TransactionStatus.CREATED.value)
    txn.status = TransactionStatus.PROCESSING.value
    wallet_service.record_event(db, txn, "TRANSACTION_PROCESSING",
                                TransactionStatus.CREATED.value,
                                TransactionStatus.PROCESSING.value)

    balance = wallet_service.debit_with_fee(db, wallet, txn, txn.description)

    if not use_campay:
        txn.status = TransactionStatus.SUCCESS.value
        txn.completed_at = _now()
        txn.provider_reference = "wd_" + uuid.uuid4().hex[:12]
        wallet_service.record_event(db, txn, "TRANSACTION_SUCCESS",
                                    TransactionStatus.PROCESSING.value,
                                    TransactionStatus.SUCCESS.value, {"balance_after": balance})

        notif = create_notification(
            db, user_id=user.id, type="WALLET_DEBITED", title="Withdrawal Successful",
            message=f"You withdrew {amount / 100:,.2f} {wallet.currency} to {dest_label}.",
            priority="HIGH", data={"transaction_id": txn.id, "amount": amount},
        )
        audit_service.record(db, "TRANSACTION_CREATED", user_id=user.id,
                             entity_type="transaction", entity_id=txn.id,
                             meta={"type": "WITHDRAW", "amount": amount, "status": "SUCCESS"})
        from app.services import limit_service
        limit_service.record_debit_against_grant(db, user.id, amount)

        db.commit()
        db.refresh(txn)

        emit_to_user(user.id, "WALLET_DEBITED", {"transaction_id": txn.id, "amount": amount})
        emit_to_user(user.id, "TRANSACTION_SUCCESS", {
            "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
            "amount": amount, "currency": wallet.currency,
        })
        emit_to_user(user.id, "WALLET_BALANCE_UPDATED", {
            "balance": balance, "currency": wallet.currency,
        })
        deliver_notification(notif)
        return txn

    # Campay path: debit held; call provider; settle or leave pending.
    db.flush()
    try:
        result = get_campay_client().withdraw(
            amount_xaf=amount_xaf,
            phone=msisdn,
            description=txn.description,
            external_reference=txn.reference,
        )
    except Exception as exc:
        reason = str(getattr(exc, "message", None) or exc)[:255]
        wallet_service.refund_charge(db, wallet, txn, f"Refund · {txn.description}")
        txn.status = TransactionStatus.FAILED.value
        txn.failure_reason = reason
        txn.completed_at = _now()
        wallet_service.record_event(
            db, txn, "TRANSACTION_FAILED",
            TransactionStatus.PROCESSING.value, TransactionStatus.FAILED.value,
            {"provider": "campay", "error": reason, "refunded": True},
        )
        audit_service.record(db, "TRANSACTION_CREATED", user_id=user.id,
                             entity_type="transaction", entity_id=txn.id,
                             meta={"type": "WITHDRAW", "amount": amount, "status": "FAILED"})
        db.commit()
        db.refresh(txn)
        raise

    campay_ref = str(result.get("reference") or "").strip()
    txn.provider_reference = campay_ref or None
    outcome = map_campay_status(result.get("status"))

    from app.services import campay_payment_service

    if campay_ref:
        campay_payment_service.record_initiate(
            db,
            reference=campay_ref,
            endpoint="withdraw",
            user_id=user.id,
            transaction_id=txn.id,
            external_reference=txn.reference,
            phone_number=msisdn,
            amount_minor=amount,
            currency=wallet.currency,
            operator=result.get("operator"),
            raw=result,
        )
        campay_payment_service.apply_status_payload(
            db, result, transaction=txn, endpoint="withdraw", notify=False
        )

    audit_service.record(db, "TRANSACTION_CREATED", user_id=user.id,
                         entity_type="transaction", entity_id=txn.id,
                         meta={
                             "type": "WITHDRAW",
                             "amount": amount,
                             "status": outcome,
                             "provider": "campay",
                             "campay_reference": campay_ref,
                         })

    if outcome == "SUCCESS":
        txn.status = TransactionStatus.SUCCESS.value
        txn.completed_at = _now()
        txn.pending_reconciliation = False
        wallet_service.record_event(
            db, txn, "TRANSACTION_SUCCESS",
            TransactionStatus.PROCESSING.value, TransactionStatus.SUCCESS.value,
            {"provider": "campay", "balance_after": balance, "campay": result},
        )
        notif = create_notification(
            db, user_id=user.id, type="WALLET_DEBITED", title="Withdrawal Successful",
            message=f"You withdrew {amount / 100:,.2f} {wallet.currency} to {dest_label}.",
            priority="HIGH", data={"transaction_id": txn.id, "amount": amount},
        )
        from app.services import limit_service
        limit_service.record_debit_against_grant(db, user.id, amount)
        payment = campay_payment_service.get_for_transaction(db, txn.id)
        if payment:
            campay_payment_service.notify_parties(db, payment, transaction=txn)
        db.commit()
        db.refresh(txn)
        emit_to_user(user.id, "WALLET_DEBITED", {"transaction_id": txn.id, "amount": amount})
        emit_to_user(user.id, "TRANSACTION_SUCCESS", {
            "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
            "amount": amount, "currency": wallet.currency,
        })
        emit_to_user(user.id, "WALLET_BALANCE_UPDATED", {
            "balance": balance, "currency": wallet.currency,
        })
        deliver_notification(notif)
        return txn

    if outcome == "FAILED":
        wallet_service.refund_charge(db, wallet, txn, f"Refund · {txn.description}")
        txn.status = TransactionStatus.FAILED.value
        txn.failure_reason = (
            str(result.get("reason") or "Campay reported the withdrawal as failed.")
        )[:255]
        txn.completed_at = _now()
        txn.pending_reconciliation = False
        wallet_service.record_event(
            db, txn, "TRANSACTION_FAILED",
            TransactionStatus.PROCESSING.value, TransactionStatus.FAILED.value,
            {"provider": "campay", "refunded": True},
        )
        payment = campay_payment_service.get_for_transaction(db, txn.id)
        if payment:
            campay_payment_service.notify_parties(db, payment, transaction=txn)
        db.commit()
        db.refresh(txn)
        emit_to_user(user.id, "TRANSACTION_FAILED", {
            "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
            "reason_code": "PROVIDER_FAILED", "retryable": True,
        })
        emit_to_user(user.id, "WALLET_BALANCE_UPDATED", {
            "balance": wallet.balance, "currency": wallet.currency,
        })
        return txn

    # PENDING — wait for reconcile / webhook.
    txn.status = TransactionStatus.PENDING.value
    txn.pending_reconciliation = True
    wallet_service.record_event(
        db, txn, "TRANSACTION_PENDING",
        TransactionStatus.PROCESSING.value, TransactionStatus.PENDING.value,
        {"provider": "campay", "campay_reference": campay_ref},
    )
    db.commit()
    db.refresh(txn)
    emit_to_user(user.id, "TRANSACTION_PENDING", {
        "transaction_id": txn.id, "reference": txn.reference, "status": txn.status,
        "amount": amount, "currency": wallet.currency,
        "provider_reference": txn.provider_reference,
    })
    emit_to_user(user.id, "WALLET_BALANCE_UPDATED", {
        "balance": balance, "currency": wallet.currency,
    })
    return txn
