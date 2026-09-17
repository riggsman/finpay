"""Money requests and beneficiaries.

Money-request funding flow
--------------------------
Actors: P-A (requester), P-B (validator/payer), CP (Campay).

1. P-A creates a request → MoneyRequest PENDING + PENDING history rows for both
   parties (``MONEY_REQUEST_OUT`` = "Request to …", ``MONEY_REQUEST_IN`` =
   "Request from …"). Those types stay through settlement so history never
   flips to SEND_MONEY / TRANSFER_RECEIVED.
2. P-B validates with PIN:
   - If P-B FinPay balance covers amount (+ send fee) → debit P-B, credit P-A
     immediately (``funding_mode=WALLET``), request PAID.
   - Else if Campay is live → CP collect on P-B's phone
     (``funding_mode=CAMPAY``, request PROCESSING). P-B confirms on device.
   - Else → INSUFFICIENT_BALANCE.
3. On Campay SUCCESS → credit P-A, mark request PAID (collect settles without
   crediting P-B's FinPay wallet). On FAILED → request FAILED.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.social import Beneficiary, MoneyRequest
from app.models.transaction import IdempotencyKey, Transaction, TransactionStatus
from app.models.user import User, UserStatus
from app.services import audit_service, fee_service, security_service, transfers_service, wallet_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_user


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _find_active_user(db: Session, identifier: str) -> User | None:
    """Resolve an active user by email or phone (flexible phone formats)."""
    ident = (identifier or "").strip()
    if not ident:
        return None

    user = (
        db.query(User)
        .filter(
            or_(User.phone == ident, User.email == ident),
            User.status == UserStatus.ACTIVE,
        )
        .one_or_none()
    )
    if user:
        return user

    if "@" in ident:
        return (
            db.query(User)
            .filter(User.email.ilike(ident), User.status == UserStatus.ACTIVE)
            .one_or_none()
        )

    # Phone: accept +237…, 237…, local 9-digit, leading 0, spaces/dashes.
    from app.services.campay_payment_service import find_user_by_msisdn

    found = find_user_by_msisdn(db, ident)
    if found and found.status == UserStatus.ACTIVE:
        return found
    return None



def _new_pending_txn(
    user_id: int,
    type_: str,
    amount: int,
    currency: str,
    description: str,
) -> Transaction:
    return Transaction(
        reference="txn_" + uuid.uuid4().hex[:16],
        user_id=user_id,
        type=type_,
        status=TransactionStatus.PENDING.value,
        amount=amount,
        fee=0,
        currency=currency,
        description=description,
    )


def _set_txn_status(
    db: Session,
    txn: Transaction | None,
    status: str,
    *,
    event: str,
    reason: str | None = None,
) -> None:
    if not txn:
        return
    prev = txn.status
    if prev == status:
        return
    txn.status = status
    if status in (
        TransactionStatus.SUCCESS.value,
        TransactionStatus.FAILED.value,
        TransactionStatus.REVERSED.value,
    ):
        txn.completed_at = txn.completed_at or _now()
    if reason:
        txn.failure_reason = reason[:255]
    wallet_service.record_event(db, txn, event, prev, status, {"reason": reason} if reason else None)


# --- Beneficiaries ---------------------------------------------------------

def add_beneficiary(db: Session, user: User, identifier: str) -> Beneficiary:
    target = _find_active_user(db, identifier)
    if not target:
        raise NotFoundError("No FinPay user found for that phone or email.",
                            code="BENEFICIARY_NOT_FOUND")
    if target.id == user.id:
        raise ValidationError("You cannot add yourself as a beneficiary.",
                              code="SELF_BENEFICIARY")
    existing = (
        db.query(Beneficiary)
        .filter(
            Beneficiary.user_id == user.id,
            Beneficiary.beneficiary_user_id == target.id,
        )
        .one_or_none()
    )
    if existing:
        return existing
    ben = Beneficiary(
        user_id=user.id,
        beneficiary_user_id=target.id,
        display_name=target.full_name or target.phone,
        phone=target.phone,
    )
    db.add(ben)
    db.flush()
    return ben


def list_beneficiaries(db: Session, user: User) -> list[Beneficiary]:
    return (
        db.query(Beneficiary)
        .filter(Beneficiary.user_id == user.id)
        .order_by(Beneficiary.display_name.asc())
        .all()
    )


def delete_beneficiary(db: Session, user: User, beneficiary_id: int) -> None:
    ben = db.get(Beneficiary, beneficiary_id)
    if not ben or ben.user_id != user.id:
        raise NotFoundError("Beneficiary not found.", code="BENEFICIARY_NOT_FOUND")
    db.delete(ben)
    db.flush()


# --- Money requests --------------------------------------------------------

def create_request(db: Session, requester: User, payer_identifier: str, amount: int,
                   note: str | None) -> MoneyRequest:
    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")
    payer = _find_active_user(db, payer_identifier)
    if not payer:
        raise NotFoundError("Payer not found.", code="PAYER_NOT_FOUND")
    if payer.id == requester.id:
        raise ValidationError("You cannot request money from yourself.",
                              code="SELF_REQUEST")

    currency = "XAF"
    requester_name = requester.full_name or requester.phone
    payer_name = payer.full_name or payer.phone

    out_txn = _new_pending_txn(
        requester.id,
        "MONEY_REQUEST_OUT",
        amount,
        currency,
        f"Request to {payer_name}",
    )
    in_txn = _new_pending_txn(
        payer.id,
        "MONEY_REQUEST_IN",
        amount,
        currency,
        f"Request from {requester_name}",
    )
    db.add(out_txn)
    db.add(in_txn)
    db.flush()
    for txn in (out_txn, in_txn):
        wallet_service.record_event(
            db, txn, "TRANSACTION_CREATED", None, TransactionStatus.CREATED.value
        )
        wallet_service.record_event(
            db,
            txn,
            "TRANSACTION_PENDING",
            TransactionStatus.CREATED.value,
            TransactionStatus.PENDING.value,
        )

    req = MoneyRequest(
        reference="req_" + uuid.uuid4().hex[:12],
        requester_id=requester.id,
        payer_id=payer.id,
        amount=amount,
        currency=currency,
        note=note,
        status="PENDING",
        transaction_id=out_txn.id,
        payer_transaction_id=in_txn.id,
    )
    db.add(req)
    db.flush()

    amount_label = f"{amount / 100:,.2f} {req.currency}"
    title = "Money Requested"
    message = f"{requester_name} requested {amount_label} from you."
    notif = create_notification(
        db,
        user_id=payer.id,
        type="MONEY_REQUESTED",
        title=title,
        message=message,
        priority="HIGH",
        data={
            "request_id": req.id,
            "amount": amount,
            "currency": req.currency,
            "status": "PENDING",
            "from": requester_name,
            "note": note,
            "transaction_id": in_txn.id,
        },
    )
    db.commit()
    db.refresh(req)
    db.refresh(notif)
    emit_to_user(payer.id, "MONEY_REQUESTED", {
        "request_id": req.id,
        "amount": amount,
        "currency": req.currency,
        "status": "PENDING",
        "from": requester_name,
        "note": note,
        "title": title,
        "message": message,
        "notification_id": notif.id,
        "transaction_id": in_txn.id,
    })
    emit_to_user(requester.id, "TRANSACTION_PENDING", {
        "transaction_id": out_txn.id,
        "reference": out_txn.reference,
        "status": out_txn.status,
        "amount": amount,
        "currency": currency,
        "type": out_txn.type,
    })
    emit_to_user(payer.id, "TRANSACTION_PENDING", {
        "transaction_id": in_txn.id,
        "reference": in_txn.reference,
        "status": in_txn.status,
        "amount": amount,
        "currency": currency,
        "type": in_txn.type,
    })
    deliver_notification(notif)
    return req


def list_requests(db: Session, user: User, direction: str) -> list[MoneyRequest]:
    q = db.query(MoneyRequest)
    if direction == "incoming":
        q = q.filter(MoneyRequest.payer_id == user.id)
    elif direction == "outgoing":
        q = q.filter(MoneyRequest.requester_id == user.id)
    else:
        q = q.filter(
            or_(MoneyRequest.payer_id == user.id, MoneyRequest.requester_id == user.id)
        )
    return q.order_by(MoneyRequest.created_at.desc()).all()


def _party_from_user(user: User | None) -> dict | None:
    if not user:
        return None
    name = (user.full_name or "").strip() or user.phone
    return {
        "id": user.id,
        "name": name,
        "phone": user.phone,
        "email": user.email,
    }


def serialize_money_request(db: Session, req: MoneyRequest) -> dict:
    """Public money-request payload including requester/payer identity."""
    requester = db.get(User, req.requester_id)
    payer = db.get(User, req.payer_id)
    return {
        "id": req.id,
        "reference": req.reference,
        "requester_id": req.requester_id,
        "payer_id": req.payer_id,
        "amount": req.amount,
        "currency": req.currency,
        "note": req.note,
        "status": req.status,
        "funding_mode": req.funding_mode,
        "transaction_id": req.transaction_id,
        "payer_transaction_id": req.payer_transaction_id,
        "collect_transaction_id": req.collect_transaction_id,
        "created_at": req.created_at,
        "resolved_at": req.resolved_at,
        "requester": _party_from_user(requester),
        "payer": _party_from_user(payer),
    }


def _load_pending(db: Session, request_id: int) -> MoneyRequest:
    req = db.get(MoneyRequest, request_id)
    if not req:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")
    if req.status != "PENDING":
        raise ConflictError("This request is no longer pending.", code="REQUEST_NOT_PENDING")
    return req


def _placeholder_txns(db: Session, req: MoneyRequest) -> tuple[Transaction | None, Transaction | None]:
    out_txn = db.get(Transaction, req.transaction_id) if req.transaction_id else None
    in_txn = db.get(Transaction, req.payer_transaction_id) if req.payer_transaction_id else None
    return out_txn, in_txn


def _mark_placeholders_processing(db: Session, req: MoneyRequest) -> None:
    out_txn, in_txn = _placeholder_txns(db, req)
    for txn in (out_txn, in_txn):
        if not txn:
            continue
        prev = txn.status
        txn.status = TransactionStatus.PROCESSING.value
        wallet_service.record_event(
            db,
            txn,
            "TRANSACTION_PROCESSING",
            prev,
            TransactionStatus.PROCESSING.value,
            {"request_id": req.id},
        )


def _notify_request_paid(
    db: Session,
    req: MoneyRequest,
    payer: User,
    requester_id: int,
    settlement_txn_id: int | None,
) -> None:
    payer_name = payer.full_name or payer.phone
    paid_title = "Request Paid"
    paid_message = f"{payer_name} paid your request of {req.amount / 100:,.2f} {req.currency}."
    notif = create_notification(
        db,
        user_id=requester_id,
        type="MONEY_REQUEST_PAID",
        title=paid_title,
        message=paid_message,
        priority="HIGH",
        data={
            "request_id": req.id,
            "transaction_id": settlement_txn_id,
            "amount": req.amount,
            "status": "PAID",
            "funding_mode": req.funding_mode,
        },
    )
    db.flush()
    db.commit()
    db.refresh(req)
    db.refresh(notif)

    emit_to_user(requester_id, "MONEY_REQUEST_PAID", {
        "request_id": req.id,
        "amount": req.amount,
        "currency": req.currency,
        "status": "PAID",
        "transaction_id": settlement_txn_id,
        "funding_mode": req.funding_mode,
        "by": payer_name,
        "title": paid_title,
        "message": paid_message,
        "notification_id": notif.id,
    })
    emit_to_user(payer.id, "MONEY_REQUEST_UPDATED", {
        "request_id": req.id,
        "amount": req.amount,
        "status": "PAID",
        "transaction_id": settlement_txn_id,
        "funding_mode": req.funding_mode,
    })
    deliver_notification(notif)


def _settle_via_wallet(
    db: Session,
    req: MoneyRequest,
    payer: User,
    requester: User,
    pin: str,
) -> MoneyRequest:
    """Debit P-B FinPay wallet and credit P-A using the PENDING history rows."""
    fee_service.ensure_enabled(db, "send_money")
    transfers_service._check_pin(payer, pin)

    fee = fee_service.compute_fee(db, "SEND_MONEY", req.amount)
    payer_wallet = wallet_service.get_wallet(db, payer.id)
    if payer_wallet.balance < req.amount + fee:
        raise ValidationError("Insufficient wallet balance.", code="INSUFFICIENT_BALANCE")
    security_service.check_limits(db, payer, req.amount)

    requester_wallet = wallet_service.get_wallet(db, requester.id)
    out_txn, in_txn = _placeholder_txns(db, req)
    if not out_txn or not in_txn:
        raise ValidationError("Request is missing ledger placeholders.", code="REQUEST_CORRUPT")

    payer_name = payer.full_name or payer.phone
    requester_name = requester.full_name or requester.phone

    # Keep request types so history stays "Request to" / "Request from".
    in_txn.type = "MONEY_REQUEST_IN"
    in_txn.description = f"Request from {requester_name}"
    out_txn.type = "MONEY_REQUEST_OUT"
    out_txn.description = f"Request to {payer_name}"

    fee_service.attach_fee(db, in_txn, "SEND_MONEY", req.amount)
    idem_key = f"moneyreq-{req.id}"
    prior = (
        db.query(IdempotencyKey)
        .filter(IdempotencyKey.key == idem_key, IdempotencyKey.user_id == payer.id)
        .one_or_none()
    )
    if not prior:
        db.add(IdempotencyKey(key=idem_key, user_id=payer.id, transaction_id=in_txn.id))

    payer_balance = wallet_service.debit_with_fee(
        db, payer_wallet, in_txn, in_txn.description
    )
    requester_balance = wallet_service.apply_ledger(
        db, requester_wallet, "CREDIT", req.amount, out_txn.id, out_txn.description
    )

    for txn in (in_txn, out_txn):
        prev = txn.status
        txn.status = TransactionStatus.SUCCESS.value
        txn.completed_at = _now()
        txn.provider_reference = txn.provider_reference or ("int_" + uuid.uuid4().hex[:12])
        wallet_service.record_event(
            db, txn, "TRANSACTION_SUCCESS", prev, TransactionStatus.SUCCESS.value
        )

    sender_notif = create_notification(
        db,
        user_id=payer.id,
        type="TRANSFER_SENT",
        title="Transfer Sent",
        message=f"You sent {req.amount / 100:,.2f} {payer_wallet.currency} to {requester_name}.",
        priority="HIGH",
        data={"transaction_id": in_txn.id, "amount": req.amount, "request_id": req.id},
    )
    recipient_notif = create_notification(
        db,
        user_id=requester.id,
        type="TRANSFER_RECEIVED",
        title="Money Received",
        message=f"You received {req.amount / 100:,.2f} {requester_wallet.currency} from {payer_name}.",
        priority="HIGH",
        data={"transaction_id": out_txn.id, "amount": req.amount, "request_id": req.id},
    )

    audit_service.record(
        db,
        "TRANSACTION_CREATED",
        user_id=payer.id,
        entity_type="transaction",
        entity_id=in_txn.id,
        meta={"type": "MONEY_REQUEST_IN", "amount": req.amount, "status": "SUCCESS", "request_id": req.id},
    )
    from app.services import limit_service

    limit_service.record_debit_against_grant(db, payer.id, req.amount)

    req.status = "PAID"
    req.funding_mode = "WALLET"
    req.resolved_at = _now()

    transfers_service._SEND_MONEY_RT[in_txn.id] = {
        "recipient_id": requester.id,
        "recipient_txn_id": out_txn.id,
        "amount": req.amount,
        "sender_name": payer_name,
        "recipient_name": requester_name,
        "sender_balance": payer_balance,
        "recipient_balance": requester_balance,
        "sender_currency": payer_wallet.currency,
        "recipient_currency": requester_wallet.currency,
        "sender_notif_id": sender_notif.id,
        "recipient_notif_id": recipient_notif.id,
    }

    _notify_request_paid(db, req, payer, requester.id, in_txn.id)
    transfers_service.publish_send_money_realtime(db, in_txn)
    return req


def _initiate_campay_collect(
    db: Session,
    req: MoneyRequest,
    payer: User,
    requester: User,
    pin: str,
    phone: str | None,
) -> MoneyRequest:
    """Start Campay collection on P-B's phone; settle later via webhook/reconcile."""
    from app.integrations.campay import (
        campay_configured,
        get_campay_client,
        minor_to_campay_amount,
        normalize_msisdn,
    )

    transfers_service._check_pin(payer, pin)
    if not campay_configured():
        raise ValidationError("Insufficient wallet balance.", code="INSUFFICIENT_BALANCE")

    msisdn = normalize_msisdn(phone or payer.phone)
    if not msisdn:
        raise ValidationError("phone is required for mobile money payment.", code="PHONE_REQUIRED")

    fee_service.ensure_enabled(db, "funding_mobile_money")
    payer_wallet = wallet_service.get_wallet(db, payer.id)
    out_txn, in_txn = _placeholder_txns(db, req)
    if not out_txn or not in_txn:
        raise ValidationError("Request is missing ledger placeholders.", code="REQUEST_CORRUPT")

    idem_key = f"moneyreq-collect-{req.id}"
    prior = (
        db.query(IdempotencyKey)
        .filter(IdempotencyKey.key == idem_key, IdempotencyKey.user_id == payer.id)
        .one_or_none()
    )
    if prior and prior.transaction_id:
        existing = db.get(Transaction, prior.transaction_id)
        if existing:
            req.collect_transaction_id = existing.id
            req.funding_mode = "CAMPAY"
            if req.status == "PENDING":
                req.status = "PROCESSING"
                _mark_placeholders_processing(db, req)
            db.commit()
            db.refresh(req)
            return req

    collect = Transaction(
        reference="txn_" + uuid.uuid4().hex[:16],
        user_id=payer.id,
        type="MONEY_REQUEST_COLLECT",
        status=TransactionStatus.CREATED.value,
        amount=req.amount,
        fee=0,
        currency=payer_wallet.currency,
        description=f"Request from {requester.full_name or requester.phone} via mobile money",
    )
    db.add(collect)
    db.flush()
    db.add(IdempotencyKey(key=idem_key, user_id=payer.id, transaction_id=collect.id))
    wallet_service.record_event(
        db, collect, "TRANSACTION_CREATED", None, TransactionStatus.CREATED.value
    )
    collect.status = TransactionStatus.PROCESSING.value
    wallet_service.record_event(
        db,
        collect,
        "TRANSACTION_PROCESSING",
        TransactionStatus.CREATED.value,
        TransactionStatus.PROCESSING.value,
        {"provider": "campay", "phone": msisdn, "request_id": req.id},
    )
    db.flush()

    try:
        result = get_campay_client().collect(
            amount_xaf=minor_to_campay_amount(req.amount),
            phone=msisdn,
            description=collect.description,
            external_reference=collect.reference,
        )
    except Exception as exc:
        collect.status = TransactionStatus.FAILED.value
        collect.failure_reason = str(getattr(exc, "message", None) or exc)[:255]
        collect.completed_at = _now()
        wallet_service.record_event(
            db,
            collect,
            "TRANSACTION_FAILED",
            TransactionStatus.PROCESSING.value,
            TransactionStatus.FAILED.value,
            {"provider": "campay", "error": collect.failure_reason},
        )
        req.status = "FAILED"
        req.funding_mode = "CAMPAY"
        req.collect_transaction_id = collect.id
        req.resolved_at = _now()
        _set_txn_status(
            db,
            out_txn,
            TransactionStatus.FAILED.value,
            event="TRANSACTION_FAILED",
            reason=collect.failure_reason,
        )
        _set_txn_status(
            db,
            in_txn,
            TransactionStatus.FAILED.value,
            event="TRANSACTION_FAILED",
            reason=collect.failure_reason,
        )
        db.commit()
        db.refresh(req)
        emit_to_user(requester.id, "MONEY_REQUEST_UPDATED", {
            "request_id": req.id, "status": "FAILED", "amount": req.amount,
        })
        emit_to_user(payer.id, "MONEY_REQUEST_UPDATED", {
            "request_id": req.id, "status": "FAILED", "amount": req.amount,
        })
        raise

    campay_ref = str(result.get("reference") or "").strip()
    if not campay_ref:
        collect.status = TransactionStatus.FAILED.value
        collect.failure_reason = "Campay did not return a transaction reference."
        collect.completed_at = _now()
        wallet_service.record_event(
            db,
            collect,
            "TRANSACTION_FAILED",
            TransactionStatus.PROCESSING.value,
            TransactionStatus.FAILED.value,
            {"provider": "campay"},
        )
        req.status = "FAILED"
        req.funding_mode = "CAMPAY"
        req.collect_transaction_id = collect.id
        req.resolved_at = _now()
        db.commit()
        db.refresh(req)
        raise ValidationError(collect.failure_reason, code="CAMPAY_ERROR")

    collect.provider_reference = campay_ref
    collect.status = TransactionStatus.PENDING.value
    collect.pending_reconciliation = True
    from app.services import campay_payment_service

    campay_payment_service.record_initiate(
        db,
        reference=campay_ref,
        endpoint="collect",
        user_id=payer.id,
        transaction_id=collect.id,
        external_reference=collect.reference,
        phone_number=msisdn,
        amount_minor=req.amount,
        currency=payer_wallet.currency,
        operator=result.get("operator"),
        raw=result,
    )
    campay_payment_service.apply_status_payload(
        db, result, transaction=collect, endpoint="collect", notify=False
    )
    wallet_service.record_event(
        db,
        collect,
        "TRANSACTION_PENDING",
        TransactionStatus.PROCESSING.value,
        TransactionStatus.PENDING.value,
        {
            "provider": "campay",
            "campay_reference": campay_ref,
            "ussd_code": result.get("ussd_code"),
            "request_id": req.id,
        },
    )

    req.status = "PROCESSING"
    req.funding_mode = "CAMPAY"
    req.collect_transaction_id = collect.id
    _mark_placeholders_processing(db, req)

    audit_service.record(
        db,
        "TRANSACTION_CREATED",
        user_id=payer.id,
        entity_type="transaction",
        entity_id=collect.id,
        meta={
            "type": collect.type,
            "amount": req.amount,
            "status": collect.status,
            "provider": "campay",
            "request_id": req.id,
        },
    )
    db.flush()

    # If Campay already returned a terminal status on collect, settle now.
    from app.integrations.campay import map_campay_status
    from app.services.reconciliation_service import apply_campay_outcome

    outcome = map_campay_status(result.get("status"))
    if outcome in ("SUCCESS", "FAILED"):
        apply_campay_outcome(db, collect, outcome, payload=result)
        db.refresh(req)
        return req

    db.commit()
    db.refresh(req)

    emit_to_user(payer.id, "TRANSACTION_PENDING", {
        "transaction_id": collect.id,
        "reference": collect.reference,
        "status": collect.status,
        "amount": collect.amount,
        "currency": collect.currency,
        "provider_reference": collect.provider_reference,
        "request_id": req.id,
        "ussd_code": result.get("ussd_code"),
    })
    emit_to_user(requester.id, "MONEY_REQUEST_UPDATED", {
        "request_id": req.id,
        "amount": req.amount,
        "status": "PROCESSING",
        "funding_mode": "CAMPAY",
        "collect_transaction_id": collect.id,
    })
    emit_to_user(payer.id, "MONEY_REQUEST_UPDATED", {
        "request_id": req.id,
        "amount": req.amount,
        "status": "PROCESSING",
        "funding_mode": "CAMPAY",
        "collect_transaction_id": collect.id,
        "ussd_code": result.get("ussd_code"),
    })
    return req


def pay_request(
    db: Session,
    payer: User,
    request_id: int,
    pin: str,
    phone: str | None = None,
) -> MoneyRequest:
    """P-B validates the request: wallet debit if funded, else Campay collect."""
    req = _load_pending(db, request_id)
    if req.payer_id != payer.id:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")

    requester = db.get(User, req.requester_id)
    if not requester or requester.status != UserStatus.ACTIVE:
        raise NotFoundError("Requester not found.", code="REQUESTER_NOT_FOUND")

    fee = fee_service.compute_fee(db, "SEND_MONEY", req.amount)
    payer_wallet = wallet_service.get_wallet(db, payer.id)
    if payer_wallet.balance >= req.amount + fee:
        return _settle_via_wallet(db, req, payer, requester, pin)
    return _initiate_campay_collect(db, req, payer, requester, pin, phone)


def find_request_by_collect_txn(db: Session, collect_txn_id: int) -> MoneyRequest | None:
    return (
        db.query(MoneyRequest)
        .filter(MoneyRequest.collect_transaction_id == collect_txn_id)
        .one_or_none()
    )


def settle_money_request_campay_success(db: Session, collect_txn: Transaction) -> MoneyRequest:
    """Campay confirmed P-B's MoMo payment → credit P-A (no FinPay credit to P-B)."""
    req = find_request_by_collect_txn(db, collect_txn.id)
    if not req:
        raise ValidationError("No money request linked to this collect.", code="REQUEST_NOT_FOUND")
    if req.status == "PAID":
        return req
    if req.status not in ("PROCESSING", "PENDING"):
        raise ConflictError("Request cannot be settled in this state.", code="REQUEST_NOT_PENDING")

    requester = db.get(User, req.requester_id)
    payer = db.get(User, req.payer_id)
    if not requester or not payer:
        raise NotFoundError("Request party not found.", code="REQUEST_NOT_FOUND")

    out_txn, in_txn = _placeholder_txns(db, req)
    if not out_txn or not in_txn:
        raise ValidationError("Request is missing ledger placeholders.", code="REQUEST_CORRUPT")

    # Mark collect SUCCESS without crediting the payer wallet — funds settled
    # externally into FinPay merchant, then credited to the requester.
    if collect_txn.status != TransactionStatus.SUCCESS.value:
        prev = collect_txn.status
        collect_txn.status = TransactionStatus.SUCCESS.value
        collect_txn.completed_at = _now()
        collect_txn.pending_reconciliation = False
        wallet_service.record_event(
            db,
            collect_txn,
            "TRANSACTION_SUCCESS",
            prev,
            TransactionStatus.SUCCESS.value,
            {"provider": "campay", "money_request_id": req.id, "skip_wallet_credit": True},
        )

    payer_name = payer.full_name or payer.phone
    requester_name = requester.full_name or requester.phone
    requester_wallet = wallet_service.get_wallet(db, requester.id)

    out_txn.type = "MONEY_REQUEST_OUT"
    out_txn.description = f"Request to {payer_name}"
    in_txn.type = "MONEY_REQUEST_IN"
    in_txn.description = f"Request from {requester_name}"
    in_txn.fee = 0
    collect_txn.description = f"Request from {requester_name} via mobile money"

    from app.models.wallet import LedgerEntry

    existing_credit = (
        db.query(LedgerEntry)
        .filter(
            LedgerEntry.transaction_id == out_txn.id,
            LedgerEntry.direction == "CREDIT",
        )
        .first()
    )
    if not existing_credit:
        requester_balance = wallet_service.apply_ledger(
            db, requester_wallet, "CREDIT", req.amount, out_txn.id, out_txn.description
        )
    else:
        requester_balance = requester_wallet.balance

    for txn in (out_txn, in_txn):
        prev = txn.status
        txn.status = TransactionStatus.SUCCESS.value
        txn.completed_at = _now()
        txn.provider_reference = txn.provider_reference or collect_txn.provider_reference
        wallet_service.record_event(
            db, txn, "TRANSACTION_SUCCESS", prev, TransactionStatus.SUCCESS.value
        )

    req.status = "PAID"
    req.funding_mode = "CAMPAY"
    req.resolved_at = _now()

    payer_sent_notif = create_notification(
        db,
        user_id=payer.id,
        type="TRANSFER_SENT",
        title="Request Paid",
        message=f"You paid {req.amount / 100:,.2f} {req.currency} to {requester_name} via mobile money.",
        priority="HIGH",
        data={"transaction_id": in_txn.id, "amount": req.amount, "request_id": req.id},
    )
    requester_recv_notif = create_notification(
        db,
        user_id=requester.id,
        type="TRANSFER_RECEIVED",
        title="Money Received",
        message=f"You received {req.amount / 100:,.2f} {req.currency} from {payer_name}.",
        priority="HIGH",
        data={"transaction_id": out_txn.id, "amount": req.amount, "request_id": req.id},
    )

    _notify_request_paid(db, req, payer, requester.id, out_txn.id)
    db.refresh(payer_sent_notif)
    db.refresh(requester_recv_notif)
    deliver_notification(payer_sent_notif)
    deliver_notification(requester_recv_notif)

    emit_to_user(requester.id, "WALLET_BALANCE_UPDATED", {
        "balance": requester_balance, "currency": requester_wallet.currency,
    })
    emit_to_user(requester.id, "TRANSFER_RECEIVED", {
        "transaction_id": out_txn.id,
        "amount": req.amount,
        "from": payer_name,
        "currency": req.currency,
    })
    return req


def settle_money_request_campay_failed(
    db: Session,
    collect_txn: Transaction,
    reason: str | None = None,
) -> MoneyRequest:
    req = find_request_by_collect_txn(db, collect_txn.id)
    if not req:
        raise ValidationError("No money request linked to this collect.", code="REQUEST_NOT_FOUND")
    if req.status in ("FAILED", "PAID", "DECLINED", "CANCELLED"):
        return req

    fail_reason = (reason or collect_txn.failure_reason or "Mobile money payment failed.")[:255]
    if collect_txn.status != TransactionStatus.FAILED.value:
        prev = collect_txn.status
        collect_txn.status = TransactionStatus.FAILED.value
        collect_txn.failure_reason = fail_reason
        collect_txn.completed_at = _now()
        collect_txn.pending_reconciliation = False
        wallet_service.record_event(
            db,
            collect_txn,
            "TRANSACTION_FAILED",
            prev,
            TransactionStatus.FAILED.value,
            {"provider": "campay", "money_request_id": req.id, "reason": fail_reason},
        )

    out_txn, in_txn = _placeholder_txns(db, req)
    _set_txn_status(
        db, out_txn, TransactionStatus.FAILED.value, event="TRANSACTION_FAILED", reason=fail_reason
    )
    _set_txn_status(
        db, in_txn, TransactionStatus.FAILED.value, event="TRANSACTION_FAILED", reason=fail_reason
    )

    req.status = "FAILED"
    req.funding_mode = "CAMPAY"
    req.resolved_at = _now()

    notif = create_notification(
        db,
        user_id=req.requester_id,
        type="MONEY_REQUEST_DECLINED",
        title="Request Payment Failed",
        message=f"Mobile money payment for your request of {req.amount / 100:,.2f} {req.currency} failed.",
        priority="HIGH",
        data={"request_id": req.id, "status": "FAILED", "reason": fail_reason},
    )
    db.commit()
    db.refresh(req)
    db.refresh(notif)
    emit_to_user(req.requester_id, "MONEY_REQUEST_UPDATED", {
        "request_id": req.id, "status": "FAILED", "amount": req.amount, "reason": fail_reason,
    })
    emit_to_user(req.payer_id, "MONEY_REQUEST_UPDATED", {
        "request_id": req.id, "status": "FAILED", "amount": req.amount, "reason": fail_reason,
    })
    deliver_notification(notif)
    return req


def decline_request(db: Session, payer: User, request_id: int) -> MoneyRequest:
    req = _load_pending(db, request_id)
    if req.payer_id != payer.id:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")
    out_txn, in_txn = _placeholder_txns(db, req)
    _set_txn_status(
        db, out_txn, TransactionStatus.FAILED.value, event="TRANSACTION_FAILED", reason="Declined"
    )
    _set_txn_status(
        db, in_txn, TransactionStatus.FAILED.value, event="TRANSACTION_FAILED", reason="Declined"
    )
    req.status = "DECLINED"
    req.resolved_at = _now()
    payer_name = payer.full_name or payer.phone
    requester_id = req.requester_id
    amount = req.amount
    currency = req.currency
    declined_title = "Request Declined"
    declined_message = f"{payer_name} declined your request of {amount / 100:,.2f} {currency}."
    notif = create_notification(
        db, user_id=requester_id, type="MONEY_REQUEST_DECLINED",
        title=declined_title,
        message=declined_message,
        priority="NORMAL", data={"request_id": req.id, "status": "DECLINED"},
    )
    db.commit()
    db.refresh(req)
    db.refresh(notif)
    emit_to_user(requester_id, "MONEY_REQUEST_DECLINED", {
        "request_id": req.id,
        "amount": amount,
        "status": "DECLINED",
        "by": payer_name,
        "title": declined_title,
        "message": declined_message,
        "notification_id": notif.id,
    })
    deliver_notification(notif)
    return req


def cancel_request(db: Session, requester: User, request_id: int) -> MoneyRequest:
    req = _load_pending(db, request_id)
    if req.requester_id != requester.id:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")
    out_txn, in_txn = _placeholder_txns(db, req)
    _set_txn_status(
        db, out_txn, TransactionStatus.FAILED.value, event="TRANSACTION_FAILED", reason="Cancelled"
    )
    _set_txn_status(
        db, in_txn, TransactionStatus.FAILED.value, event="TRANSACTION_FAILED", reason="Cancelled"
    )
    payer_id = req.payer_id
    req.status = "CANCELLED"
    req.resolved_at = _now()
    db.commit()
    db.refresh(req)
    emit_to_user(payer_id, "MONEY_REQUEST_UPDATED", {
        "request_id": req.id, "amount": req.amount, "status": "CANCELLED",
    })
    return req
