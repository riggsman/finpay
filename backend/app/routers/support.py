from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.support import (
    DisputeCreateRequest,
    DisputePublic,
    MessageCreateRequest,
    SupportMessagePublic,
    TicketCreateRequest,
    TicketDetailPublic,
    TicketPublic,
)
from app.services import support_service

router = APIRouter(prefix="/support", tags=["support"])


@router.post("/tickets", response_model=TicketPublic)
def create_ticket(
    payload: TicketCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = support_service.create_ticket(
        db, current_user, payload.subject, payload.category, payload.message
    )
    return TicketPublic.model_validate(ticket)


@router.get("/tickets", response_model=list[TicketPublic])
def list_tickets(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [TicketPublic.model_validate(t) for t in support_service.list_tickets(db, current_user)]


@router.get("/tickets/{ticket_id}", response_model=TicketDetailPublic)
def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket, messages = support_service.get_ticket(db, current_user, ticket_id)
    detail = TicketDetailPublic.model_validate(ticket)
    detail.messages = [SupportMessagePublic.model_validate(m) for m in messages]
    return detail


@router.post("/tickets/{ticket_id}/messages", response_model=SupportMessagePublic)
def add_message(
    ticket_id: int,
    payload: MessageCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    msg = support_service.add_message(db, current_user, ticket_id, payload.body)
    return SupportMessagePublic.model_validate(msg)


@router.post("/tickets/{ticket_id}/close", response_model=TicketPublic)
def close_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = support_service.close_ticket(db, current_user, ticket_id)
    return TicketPublic.model_validate(ticket)


@router.post("/disputes", response_model=DisputePublic)
def create_dispute(
    payload: DisputeCreateRequest,
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dispute = support_service.create_dispute(
        db, current_user, transaction_id, payload.reason, payload.description
    )
    return DisputePublic.model_validate(dispute)


@router.get("/disputes", response_model=list[DisputePublic])
def list_disputes(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [DisputePublic.model_validate(d) for d in support_service.list_disputes(db, current_user)]
