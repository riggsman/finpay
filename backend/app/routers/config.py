from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import fee_service

router = APIRouter(tags=["config"])


@router.get("/config")
def get_config(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Fee and feature configuration for the client to cache (SRS 71.4)."""
    return fee_service.get_client_config(db)


@router.get("/fees/quote")
def fee_quote(
    operation: str = Query(...),
    amount: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return fee_service.quote(db, operation.upper(), amount)
