import datetime as dt
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.support import SupportMessage, SupportTicket, TransactionDispute
from app.models.transaction import Transaction
from app.models.user import User
from app.services.notification_service import create_notification, deliver_notification

AGENT_ACK = (
    "Thanks for reaching out. A support agent has received your request and "
    "will follow up shortly. Your ticket is now in progress."
)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --- Tickets ---------------------------------------------------------------

def create_ticket(db: Session, user: User, subject: str, category: str,
                  message: str) -> SupportTicket:
    ticket = SupportTicket(
        reference="tkt_" + uuid.uuid4().hex[:12],
        user_id=user.id,
        subject=subject,
        category=category or "general",
        status="IN_PROGRESS",
    )
    db.add(ticket)
    db.flush()
    db.add(SupportMessage(ticket_id=ticket.id, sender="user", body=message))
    db.add(SupportMessage(ticket_id=ticket.id, sender="agent", body=AGENT_ACK))

    notif = create_notification(
        db, user_id=user.id, type="SUPPORT_TICKET_UPDATE", title="Support Ticket Created",
        message=f"Ticket {ticket.reference} was created and is now in progress.",
        priority="NORMAL", data={"ticket_id": ticket.id},
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


# --- Disputes --------------------------------------------------------------

def create_dispute(db: Session, user: User, transaction_id: int, reason: str,
                   description: str | None) -> TransactionDispute:
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.user_id != user.id:
        raise NotFoundError("Transaction not found.", code="TRANSACTION_NOT_FOUND")

    existing = (
        db.query(TransactionDispute)
        .filter(TransactionDispute.transaction_id == transaction_id)
        .one_or_none()
    )
    if existing:
        raise ConflictError("A dispute already exists for this transaction.",
                            code="DISPUTE_EXISTS")

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
        db, user_id=user.id, type="DISPUTE_UPDATE", title="Dispute Submitted",
        message=f"Your dispute {dispute.reference} for {txn.reference} has been received.",
        priority="HIGH", data={"dispute_id": dispute.id, "transaction_id": transaction_id},
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
