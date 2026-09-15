from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.notification import Notification
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import TransactionPublic
from app.services import wallet_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    wallet = wallet_service.get_wallet(db, current_user.id)
    db.commit()
    recent = (
        db.query(Transaction)
        .filter(Transaction.user_id == current_user.id)
        .order_by(Transaction.created_at.desc())
        .limit(5)
        .all()
    )
    unread = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .count()
    )
    return {
        "user": {
            "id": current_user.id,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
        },
        "wallet": {"balance": wallet.balance, "currency": wallet.currency},
        "unread_notifications": unread,
        "recent_transactions": [
            TransactionPublic.model_validate(t).model_dump(mode="json") for t in recent
        ],
    }
