import datetime as dt
import json
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.support import SupportMessage, SupportTicket, TransactionDispute
from app.models.transaction import Transaction
from app.models.user import User
from app.services import support_media
from app.services.notification_service import create_notification, deliver_notification

AGENT_ACK = (
    "Thanks for reaching out. A support agent has received your request and "
    "will follow up shortly. Your ticket is now in progress."
)

TICKET_STATUSES = {"OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_context(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def ticket_to_public(ticket: SupportTicket) -> dict:
    return {
        "id": ticket.id,
        "reference": ticket.reference,
        "subject": ticket.subject,
        "category": ticket.category,
        "status": ticket.status,
        "page_url": ticket.page_url,
        "user_agent": ticket.user_agent,
        "context": _parse_context(ticket.context_json),
        "has_screenshot": bool(ticket.screenshot_path),
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }


def ticket_to_admin_public(ticket: SupportTicket, user: User | None) -> dict:
    data = ticket_to_public(ticket)
    data.update(
        {
            "user_id": ticket.user_id,
            "user_name": (user.full_name if user else None) or (user.phone if user else None),
            "user_phone": user.phone if user else None,
            "user_email": user.email if user else None,
        }
    )
    return data


# --- Tickets ---------------------------------------------------------------

def create_ticket(
    db: Session,
    user: User,
    subject: str,
    category: str,
    message: str,
    *,
    page_url: str | None = None,
    user_agent: str | None = None,
    context: dict | None = None,
    screenshot_base64: str | None = None,
) -> SupportTicket:
    screenshot_ref = None
    if screenshot_base64:
        screenshot_ref = support_media.save_screenshot(user.id, screenshot_base64)

    context_json = None
    if context is not None:
        try:
            context_json = json.dumps(context)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Invalid issue context.", code="SUPPORT_CONTEXT_INVALID") from exc

    ticket = SupportTicket(
        reference="tkt_" + uuid.uuid4().hex[:12],
        user_id=user.id,
        subject=subject,
        category=category or "general",
        status="IN_PROGRESS",
        page_url=page_url[:500] if page_url else None,
        user_agent=user_agent[:500] if user_agent else None,
        context_json=context_json,
        screenshot_path=screenshot_ref,
    )
    db.add(ticket)
    db.flush()
    db.add(SupportMessage(ticket_id=ticket.id, sender="user", body=message))
    db.add(SupportMessage(ticket_id=ticket.id, sender="agent", body=AGENT_ACK))

    notif = create_notification(
        db,
        user_id=user.id,
        type="SUPPORT_TICKET_UPDATE",
        title="Support Ticket Created",
        message=f"Ticket {ticket.reference} was created and is now in progress.",
        priority="NORMAL",
        data={"ticket_id": ticket.id},
    )
    db.commit()
    db.refresh(ticket)
    deliver_notification(notif)
    return ticket


def list_tickets(db: Session, user: User) -> list[SupportTicket]:
    return (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == user.id)
        .order_by(SupportTicket.updated_at.desc())
        .all()
    )


def _owned_ticket(db: Session, user: User, ticket_id: int) -> SupportTicket:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or ticket.user_id != user.id:
        raise NotFoundError("Ticket not found.", code="TICKET_NOT_FOUND")
    return ticket


def get_ticket(db: Session, user: User, ticket_id: int) -> tuple[SupportTicket, list[SupportMessage]]:
    ticket = _owned_ticket(db, user, ticket_id)
    messages = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == ticket.id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )
    return ticket, messages


def add_message(db: Session, user: User, ticket_id: int, body: str) -> SupportMessage:
    ticket = _owned_ticket(db, user, ticket_id)
    if ticket.status == "CLOSED":
        ticket.status = "IN_PROGRESS"
    msg = SupportMessage(ticket_id=ticket.id, sender="user", body=body)
    db.add(msg)
    ticket.updated_at = _now()
    db.commit()
    db.refresh(msg)
    return msg


def close_ticket(db: Session, user: User, ticket_id: int) -> SupportTicket:
    ticket = _owned_ticket(db, user, ticket_id)
    ticket.status = "CLOSED"
    db.commit()
    db.refresh(ticket)
    return ticket


def get_ticket_screenshot(db: Session, user: User, ticket_id: int):
    ticket = _owned_ticket(db, user, ticket_id)
    if not ticket.screenshot_path:
        raise NotFoundError("Screenshot not found.", code="SUPPORT_SCREENSHOT_NOT_FOUND")
    return support_media.resolve_path(ticket.screenshot_path)


# --- Admin tickets ---------------------------------------------------------

def list_tickets_admin(
    db: Session,
    *,
    status: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[SupportTicket]:
    q = db.query(SupportTicket)
    if status:
        q = q.filter(SupportTicket.status == status)
    if user_id:
        q = q.filter(SupportTicket.user_id == user_id)
    return (
        q.order_by(SupportTicket.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_ticket_admin(
    db: Session, ticket_id: int
) -> tuple[SupportTicket, list[SupportMessage], User | None]:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise NotFoundError("Ticket not found.", code="TICKET_NOT_FOUND")
    messages = (
        db.query(SupportMessage)
        .filter(SupportMessage.ticket_id == ticket.id)
        .order_by(SupportMessage.created_at.asc())
        .all()
    )
    user = db.get(User, ticket.user_id)
    return ticket, messages, user


def admin_reply(db: Session, admin: User, ticket_id: int, body: str) -> SupportMessage:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise NotFoundError("Ticket not found.", code="TICKET_NOT_FOUND")
    if not (body or "").strip():
        raise ValidationError("Reply body is required.", code="SUPPORT_REPLY_REQUIRED")

    if ticket.status in {"OPEN", "RESOLVED", "CLOSED"}:
        ticket.status = "IN_PROGRESS"

    msg = SupportMessage(ticket_id=ticket.id, sender="agent", body=body.strip())
    db.add(msg)
    ticket.updated_at = _now()

    notif = create_notification(
        db,
        user_id=ticket.user_id,
        type="SUPPORT_TICKET_REPLY",
        title="Support replied",
        message=f"New reply on ticket {ticket.reference}.",
        priority="NORMAL",
        data={"ticket_id": ticket.id},
    )
    db.commit()
    db.refresh(msg)
    deliver_notification(notif)
    return msg


def admin_update_status(db: Session, ticket_id: int, status: str) -> SupportTicket:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise NotFoundError("Ticket not found.", code="TICKET_NOT_FOUND")
    normalized = (status or "").strip().upper()
    if normalized not in TICKET_STATUSES:
        raise ValidationError(
            f"Status must be one of: {', '.join(sorted(TICKET_STATUSES))}.",
            code="SUPPORT_STATUS_INVALID",
        )
    ticket.status = normalized
    ticket.updated_at = _now()
    db.commit()
    db.refresh(ticket)
    return ticket


def get_ticket_screenshot_admin(db: Session, ticket_id: int):
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket or not ticket.screenshot_path:
        raise NotFoundError("Screenshot not found.", code="SUPPORT_SCREENSHOT_NOT_FOUND")
    return support_media.resolve_path(ticket.screenshot_path)


# --- Disputes --------------------------------------------------------------

def create_dispute(
    db: Session, user: User, transaction_id: int, reason: str, description: str | None
) -> TransactionDispute:
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.user_id != user.id:
        raise NotFoundError("Transaction not found.", code="TRANSACTION_NOT_FOUND")

    existing = (
        db.query(TransactionDispute)
        .filter(TransactionDispute.transaction_id == transaction_id)
        .one_or_none()
    )
    if existing:
        raise ConflictError(
            "A dispute already exists for this transaction.", code="DISPUTE_EXISTS"
        )

    if not reason:
        raise ValidationError("A dispute reason is required.", code="DISPUTE_REASON_REQUIRED")

    dispute = TransactionDispute(
        reference="dsp_" + uuid.uuid4().hex[:12],
        user_id=user.id,
        transaction_id=transaction_id,
        reason=reason,
        description=description,
        status="OPEN",
    )
    db.add(dispute)
    db.flush()

    notif = create_notification(
        db,
        user_id=user.id,
        type="DISPUTE_UPDATE",
        title="Dispute Submitted",
        message=f"Your dispute {dispute.reference} for {txn.reference} has been received.",
        priority="HIGH",
        data={"dispute_id": dispute.id, "transaction_id": transaction_id},
    )
    db.commit()
    db.refresh(dispute)
    deliver_notification(notif)
    return dispute


def list_disputes(db: Session, user: User) -> list[TransactionDispute]:
    return (
        db.query(TransactionDispute)
        .filter(TransactionDispute.user_id == user.id)
        .order_by(TransactionDispute.created_at.desc())
        .all()
    )
