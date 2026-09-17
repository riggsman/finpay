"""Persist and finalize Campay payment rows; email sender and receiver."""

from __future__ import annotations

import datetime as dt
import json
import re

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.integrations.campay import map_campay_status, normalize_msisdn
from app.models.campay import CampayPayment
from app.models.transaction import Transaction
from app.models.user import User
from app.notifications.email import send_email
from app.services.notification_service import create_notification, deliver_notification

logger = get_logger("finpay.campay_payment")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _digits(phone: str | None) -> str:
    return re.sub(r"\D+", "", phone or "")


def find_user_by_msisdn(db: Session, phone: str | None) -> User | None:
    if not phone:
        return None
    try:
        msisdn = normalize_msisdn(phone)
    except Exception:
        msisdn = _digits(phone)
    variants = {msisdn, "+" + msisdn if not msisdn.startswith("+") else msisdn}
    if msisdn.startswith("237") and len(msisdn) == 12:
        variants.add("+" + msisdn)
        variants.add(msisdn[3:])  # local 9-digit
        variants.add("0" + msisdn[3:])
    filters = [User.phone == v for v in variants if v]
    if not filters:
        return None
    return db.query(User).filter(or_(*filters)).one_or_none()


def get_by_reference(db: Session, reference: str | None) -> CampayPayment | None:
    if not reference:
        return None
    return (
        db.query(CampayPayment)
        .filter(CampayPayment.reference == str(reference).strip())
        .one_or_none()
    )


def get_by_external_reference(db: Session, external_reference: str | None) -> CampayPayment | None:
    if not external_reference:
        return None
    return (
        db.query(CampayPayment)
        .filter(CampayPayment.external_reference == str(external_reference).strip())
        .one_or_none()
    )


def get_for_transaction(db: Session, transaction_id: int) -> CampayPayment | None:
    return (
        db.query(CampayPayment)
        .filter(CampayPayment.transaction_id == transaction_id)
        .one_or_none()
    )


def record_initiate(
    db: Session,
    *,
    reference: str,
    endpoint: str,
    user_id: int | None,
    transaction_id: int | None,
    external_reference: str | None,
    phone_number: str | None,
    amount_minor: int | None = None,
    currency: str = "XAF",
    operator: str | None = None,
    raw: dict | None = None,
) -> CampayPayment:
    """Create or refresh a Campay payment row right after collect/withdraw."""
    ref = str(reference).strip()
    row = get_by_reference(db, ref)
    phone = None
    if phone_number:
        try:
            phone = normalize_msisdn(phone_number)
        except Exception:
            phone = _digits(phone_number)

    amount_str = None
    if amount_minor is not None:
        amount_str = f"{int(amount_minor) / 100:.2f}"

    if row is None:
        row = CampayPayment(
            reference=ref,
            endpoint=(endpoint or "collect").lower(),
            user_id=user_id,
            transaction_id=transaction_id,
            external_reference=external_reference,
            phone_number=phone,
            amount=amount_str,
            amount_minor=amount_minor,
            currency=currency or "XAF",
            operator=operator,
            status="PENDING",
            mapped_status="PENDING",
            raw_json=json.dumps(raw) if raw else None,
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(row)
    else:
        row.endpoint = (endpoint or row.endpoint or "collect").lower()
        if user_id is not None:
            row.user_id = user_id
        if transaction_id is not None:
            row.transaction_id = transaction_id
        if external_reference:
            row.external_reference = external_reference
        if phone:
            row.phone_number = phone
        if amount_minor is not None:
            row.amount_minor = amount_minor
            row.amount = amount_str
        if operator:
            row.operator = operator
        if raw:
            row.raw_json = json.dumps(raw)
        row.updated_at = _now()
    db.flush()
    return row


def apply_status_payload(
    db: Session,
    payload: dict,
    *,
    transaction: Transaction | None = None,
    endpoint: str | None = None,
    user_id: int | None = None,
    notify: bool = True,
) -> CampayPayment | None:
    """Upsert Campay fields from a status/webhook payload and sync the FinPay txn."""
    if not isinstance(payload, dict):
        return None

    reference = str(
        payload.get("reference")
        or payload.get("transaction_reference")
        or (transaction.provider_reference if transaction else "")
        or ""
    ).strip()
    if not reference:
        return None

    external = payload.get("external_reference")
    if external is not None:
        external = str(external).strip() or None

    row = get_by_reference(db, reference)
    if row is None and external:
        row = get_by_external_reference(db, external)
    if row is None and transaction is not None:
        row = get_for_transaction(db, transaction.id)

    status_raw = str(payload.get("status") or "PENDING")
    mapped = map_campay_status(status_raw)
    amount = payload.get("amount")
    amount_str = str(amount) if amount is not None and amount != "" else None
    currency = str(payload.get("currency") or "XAF")
    operator = payload.get("operator")
    operator_reference = payload.get("operator_reference")
    phone = payload.get("phone_number") or payload.get("from") or payload.get("to")
    reason = payload.get("reason") or payload.get("failure_reason")
    code = payload.get("code")
    ep = (endpoint or payload.get("endpoint") or (row.endpoint if row else "collect") or "collect")
    ep = str(ep).lower()

    phone_norm = None
    if phone:
        try:
            phone_norm = normalize_msisdn(str(phone))
        except Exception:
            phone_norm = _digits(str(phone))

    amount_minor = None
    if transaction is not None:
        amount_minor = int(transaction.amount)
    elif amount_str:
        try:
            amount_minor = int(round(float(amount_str) * 100))
        except Exception:
            amount_minor = None

    if row is None:
        row = CampayPayment(
            reference=reference,
            endpoint=ep,
            user_id=user_id or (transaction.user_id if transaction else None),
            transaction_id=transaction.id if transaction else None,
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(row)
    else:
        if transaction is not None and not row.transaction_id:
            row.transaction_id = transaction.id
        if user_id is not None:
            row.user_id = user_id
        elif transaction is not None and not row.user_id:
            row.user_id = transaction.user_id

    was_final = row.mapped_status in ("SUCCESS", "FAILED") and row.finalized_at is not None

    row.reference = reference
    row.endpoint = ep
    row.status = status_raw.upper() if status_raw else row.status
    row.mapped_status = mapped
    if amount_str:
        row.amount = amount_str
    if amount_minor is not None:
        row.amount_minor = amount_minor
    row.currency = currency
    if operator:
        row.operator = str(operator)
    if operator_reference is not None:
        row.operator_reference = str(operator_reference)[:80]
    if external:
        row.external_reference = external
    if phone_norm:
        row.phone_number = phone_norm
    if reason is not None:
        row.reason = str(reason)[:255]
    if code is not None:
        row.code = str(code)[:64]
    row.raw_json = json.dumps(payload)
    row.updated_at = _now()

    # Keep FinPay transaction fields aligned when linked.
    txn = transaction
    if txn is None and row.transaction_id:
        txn = db.get(Transaction, row.transaction_id)
    if txn is not None:
        txn.provider_reference = reference
        if mapped == "FAILED" and row.reason:
            txn.failure_reason = row.reason[:255]
        # Enrich description with operator / phone once known.
        bits = []
        if row.operator:
            bits.append(str(row.operator))
        if row.phone_number:
            bits.append(row.phone_number)
        if bits and txn.description and "·" not in (txn.description or ""):
            txn.description = f"{txn.description} · {' / '.join(bits)}"[:255]

    newly_final = mapped in ("SUCCESS", "FAILED") and not was_final
    if newly_final:
        row.finalized_at = _now()

    db.flush()

    if newly_final and notify:
        notify_parties(db, row, transaction=txn)

    return row


def notify_parties(
    db: Session,
    payment: CampayPayment,
    *,
    transaction: Transaction | None = None,
) -> None:
    """Email FinPay initiator and MoMo counterparty (if they have a FinPay account)."""
    if payment.notified_at:
        return
    if payment.mapped_status not in ("SUCCESS", "FAILED"):
        return

    txn = transaction
    if txn is None and payment.transaction_id:
        txn = db.get(Transaction, payment.transaction_id)

    initiator = db.get(User, payment.user_id) if payment.user_id else None
    if initiator is None and txn is not None:
        initiator = db.get(User, txn.user_id)

    counterparty = find_user_by_msisdn(db, payment.phone_number)

    is_collect = (payment.endpoint or "collect").lower() == "collect"
    ok = payment.mapped_status == "SUCCESS"
    amount_label = payment.amount or (
        f"{(payment.amount_minor or (txn.amount if txn else 0)) / 100:,.2f}"
    )
    currency = payment.currency or (txn.currency if txn else "XAF")
    status_word = "successful" if ok else "failed"
    reason_line = f"\nReason: {payment.reason}" if payment.reason and not ok else ""
    ref_line = (
        f"Campay reference: {payment.reference}\n"
        f"External reference: {payment.external_reference or (txn.reference if txn else '—')}\n"
        f"Operator: {payment.operator or '—'} ({payment.operator_reference or '—'})\n"
        f"Phone: {payment.phone_number or '—'}"
    )

    if is_collect:
        # MoMo payer = sender; FinPay user = receiver of wallet credit
        sender, receiver = counterparty, initiator
        title_ok = "Mobile money deposit successful"
        title_fail = "Mobile money deposit failed"
        sender_msg = (
            f"Your mobile money payment of {amount_label} {currency} was {status_word}."
            f"{reason_line}\n\n{ref_line}"
        )
        receiver_msg = (
            f"A mobile money collection of {amount_label} {currency} was {status_word}."
            f"{reason_line}\n\n{ref_line}"
        )
    else:
        # FinPay user = sender; MoMo phone = receiver
        sender, receiver = initiator, counterparty
        title_ok = "Withdrawal successful"
        title_fail = "Withdrawal failed"
        sender_msg = (
            f"Your withdrawal of {amount_label} {currency} was {status_word}."
            f"{reason_line}\n\n{ref_line}"
        )
        receiver_msg = (
            f"You received a mobile money payout of {amount_label} {currency} "
            f"({status_word}).{reason_line}\n\n{ref_line}"
        )

    title = title_ok if ok else title_fail
    ntype = "CAMPAY_PAYMENT_SUCCESS" if ok else "CAMPAY_PAYMENT_FAILED"
    service_key = "add_money" if is_collect else "withdraw"

    def _notify_user(user: User | None, message: str, role: str) -> None:
        if not user:
            return
        notif = create_notification(
            db,
            user_id=user.id,
            type=ntype,
            title=title,
            message=message[:500],
            priority="HIGH",
            data={
                "campay_reference": payment.reference,
                "transaction_id": payment.transaction_id,
                "status": payment.mapped_status,
                "role": role,
                "service": service_key,
                "category": service_key,
            },
            event_id=f"campay-{payment.reference}-{role}-{payment.mapped_status}",
        )
        # Persist before email delivery.
        db.flush()
        deliver_notification(notif)
        if user.email:
            send_email(user.email, f"[FinPay] {title}", message)

    # Always notify distinct parties.
    if sender and receiver and sender.id == receiver.id:
        _notify_user(sender, receiver_msg if is_collect else sender_msg, "both")
    else:
        _notify_user(sender, sender_msg, "sender")
        _notify_user(receiver, receiver_msg, "receiver")

    payment.notified_at = _now()
    db.flush()
