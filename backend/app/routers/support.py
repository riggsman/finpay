from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
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


def _ticket_public(ticket) -> TicketPublic:
    return TicketPublic.model_validate(support_service.ticket_to_public(ticket))


def _ticket_detail(ticket, messages) -> TicketDetailPublic:
    detail = TicketDetailPublic.model_validate(support_service.ticket_to_public(ticket))
    detail.messages = [SupportMessagePublic.model_validate(m) for m in messages]
    return detail


@router.post("/tickets", response_model=TicketPublic)
def create_ticket(
    payload: TicketCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket = support_service.create_ticket(
        db,
        current_user,
        payload.subject,
        payload.category,
        payload.message,
        page_url=payload.page_url,
        user_agent=payload.user_agent,
        context=payload.context,
        screenshot_base64=payload.screenshot_base64,
    )
    return _ticket_public(ticket)


@router.get("/tickets", response_model=list[TicketPublic])
def list_tickets(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_ticket_public(t) for t in support_service.list_tickets(db, current_user)]


@router.get("/tickets/{ticket_id}", response_model=TicketDetailPublic)
def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ticket, messages = support_service.get_ticket(db, current_user, ticket_id)
    return _ticket_detail(ticket, messages)


@router.get("/tickets/{ticket_id}/screenshot")
def get_ticket_screenshot(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    path = support_service.get_ticket_screenshot(db, current_user, ticket_id)
    media = (
        "image/jpeg"
        if path.suffix.lower() in (".jpg", ".jpeg")
        else f"image/{path.suffix.lstrip('.')}"
    )
    return FileResponse(path, media_type=media, filename=Path(path).name)


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
    return _ticket_public(ticket)


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
