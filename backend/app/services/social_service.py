import datetime as dt
import uuid

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.social import Beneficiary, MoneyRequest
from app.models.user import User, UserStatus
from app.services import transfers_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_user


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _find_active_user(db: Session, identifier: str) -> User | None:
    return (
        db.query(User)
        .filter(
            or_(User.phone == identifier, User.email == identifier),
            User.status == UserStatus.ACTIVE,
        )
        .one_or_none()
    )


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

    req = MoneyRequest(
        reference="req_" + uuid.uuid4().hex[:12],
        requester_id=requester.id,
        payer_id=payer.id,
        amount=amount,
        note=note,
        status="PENDING",
    )
    db.add(req)
    db.flush()

    requester_name = requester.full_name or requester.phone
    notif = create_notification(
        db, user_id=payer.id, type="MONEY_REQUESTED", title="Money Requested",
        message=f"{requester_name} requested {amount / 100:,.2f} {req.currency} from you.",
        priority="HIGH", data={"request_id": req.id, "amount": amount},
    )
    db.commit()
    db.refresh(req)
    emit_to_user(payer.id, "MONEY_REQUESTED", {
        "request_id": req.id, "amount": amount, "from": requester_name,
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


def _load_pending(db: Session, request_id: int) -> MoneyRequest:
    req = db.get(MoneyRequest, request_id)
    if not req:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")
    if req.status != "PENDING":
        raise ConflictError("This request is no longer pending.", code="REQUEST_NOT_PENDING")
    return req


def pay_request(db: Session, payer: User, request_id: int, pin: str) -> MoneyRequest:
    req = _load_pending(db, request_id)
    if req.payer_id != payer.id:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")

    requester = db.get(User, req.requester_id)
    if not requester:
        raise NotFoundError("Requester not found.", code="REQUESTER_NOT_FOUND")

    # Reuse the transfer engine (PIN, limits, idempotency, realtime, ledger).
    txn = transfers_service.send_money(
        db, payer, requester.phone, req.amount, pin,
        idempotency_key=f"moneyreq-{req.id}",
    )

    req.status = "PAID"
    req.transaction_id = txn.id
    req.resolved_at = _now()

    payer_name = payer.full_name or payer.phone
    notif = create_notification(
        db, user_id=req.requester_id, type="MONEY_REQUEST_PAID",
        title="Request Paid",
        message=f"{payer_name} paid your request of {req.amount / 100:,.2f} {req.currency}.",
        priority="HIGH", data={"request_id": req.id, "transaction_id": txn.id},
    )
    db.commit()
    db.refresh(req)
    emit_to_user(req.requester_id, "MONEY_REQUEST_PAID", {
        "request_id": req.id, "amount": req.amount, "by": payer_name,
    })
    deliver_notification(notif)
    return req


def decline_request(db: Session, payer: User, request_id: int) -> MoneyRequest:
    req = _load_pending(db, request_id)
    if req.payer_id != payer.id:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")
    req.status = "DECLINED"
    req.resolved_at = _now()
    payer_name = payer.full_name or payer.phone
    notif = create_notification(
        db, user_id=req.requester_id, type="MONEY_REQUEST_DECLINED",
        title="Request Declined",
        message=f"{payer_name} declined your request of {req.amount / 100:,.2f} {req.currency}.",
        priority="NORMAL", data={"request_id": req.id},
    )
    db.commit()
    db.refresh(req)
    deliver_notification(notif)
    return req


def cancel_request(db: Session, requester: User, request_id: int) -> MoneyRequest:
    req = _load_pending(db, request_id)
    if req.requester_id != requester.id:
        raise NotFoundError("Request not found.", code="REQUEST_NOT_FOUND")
    req.status = "CANCELLED"
    req.resolved_at = _now()
    db.commit()
    db.refresh(req)
    return req
