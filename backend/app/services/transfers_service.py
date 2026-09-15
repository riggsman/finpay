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


def send_money(db: Session, sender: User, recipient_identifier: str, amount: int,
               pin: str, idempotency_key: str | None) -> Transaction:
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

    # Sender (debit) transaction.
    sender_txn = _new_txn(sender.id, "SEND_MONEY", amount, sender_wallet.currency,
                          f"Transfer to {recipient_name}")
    sender_txn.fee = fee
    db.add(sender_txn)
    db.flush()
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

    sender_balance = wallet_service.apply_ledger(
        db, sender_wallet, "DEBIT", amount + fee, sender_txn.id, sender_txn.description
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
    db.commit()
    db.refresh(sender_txn)

    # Realtime: sender side.
    emit_to_user(sender.id, "TRANSFER_SENT", {
        "transaction_id": sender_txn.id, "amount": amount, "to": recipient_name,
    })
    emit_to_user(sender.id, "TRANSACTION_SUCCESS", {
        "transaction_id": sender_txn.id, "reference": sender_txn.reference,
        "status": sender_txn.status, "amount": amount, "currency": sender_wallet.currency,
    })
    emit_to_user(sender.id, "WALLET_BALANCE_UPDATED", {
        "balance": sender_balance, "currency": sender_wallet.currency,
    })
    deliver_notification(sender_notif)

    # Realtime: recipient side (they may be connected in another session).
    emit_to_user(recipient.id, "TRANSFER_RECEIVED", {
        "transaction_id": recipient_txn.id, "amount": amount, "from": sender_name,
    })
    emit_to_user(recipient.id, "WALLET_BALANCE_UPDATED", {
        "balance": recipient_balance, "currency": recipient_wallet.currency,
    })
    deliver_notification(recipient_notif)

    return sender_txn


def withdraw(db: Session, user: User, amount: int, destination: str, pin: str,
             idempotency_key: str | None) -> Transaction:
    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")
    fee_service.ensure_enabled(db, "withdraw")
    _check_pin(user, pin)

    hit = _idempotent_hit(db, user.id, idempotency_key)
    if hit:
        return hit

    fee = fee_service.compute_fee(db, "WITHDRAW", amount)
    wallet = wallet_service.get_wallet(db, user.id)
    if wallet.balance < amount + fee:
        raise ValidationError("Insufficient wallet balance.", code="INSUFFICIENT_BALANCE")
    security_service.check_limits(db, user, amount)

    txn = _new_txn(user.id, "WITHDRAW", amount, wallet.currency,
                   f"Withdrawal to {destination}")
    txn.fee = fee
    db.add(txn)
    db.flush()
    if idempotency_key:
        db.add(IdempotencyKey(key=idempotency_key, user_id=user.id, transaction_id=txn.id))

    wallet_service.record_event(db, txn, "TRANSACTION_CREATED", None,
                                TransactionStatus.CREATED.value)
    txn.status = TransactionStatus.PROCESSING.value
    wallet_service.record_event(db, txn, "TRANSACTION_PROCESSING",
                                TransactionStatus.CREATED.value,
                                TransactionStatus.PROCESSING.value)

    balance = wallet_service.apply_ledger(db, wallet, "DEBIT", amount + fee, txn.id,
                                          txn.description)
    txn.status = TransactionStatus.SUCCESS.value
    txn.completed_at = _now()
    txn.provider_reference = "wd_" + uuid.uuid4().hex[:12]
    wallet_service.record_event(db, txn, "TRANSACTION_SUCCESS",
                                TransactionStatus.PROCESSING.value,
                                TransactionStatus.SUCCESS.value, {"balance_after": balance})

    notif = create_notification(
        db, user_id=user.id, type="WALLET_DEBITED", title="Withdrawal Successful",
        message=f"You withdrew {amount / 100:,.2f} {wallet.currency} to {destination}.",
        priority="HIGH", data={"transaction_id": txn.id, "amount": amount},
    )
    audit_service.record(db, "TRANSACTION_CREATED", user_id=user.id,
                         entity_type="transaction", entity_id=txn.id,
                         meta={"type": "WITHDRAW", "amount": amount, "status": "SUCCESS"})

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
