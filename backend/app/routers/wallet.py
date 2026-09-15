from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.transaction import TransactionPublic
from app.schemas.wallet import AddMoneyRequest, WalletResponse
from app.services import wallet_service

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("", response_model=WalletResponse)
def get_wallet(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = wallet_service.get_wallet(db, current_user.id)
    db.commit()
    return WalletResponse.model_validate(wallet)


@router.post("/add-money", response_model=TransactionPublic)
def add_money(
    payload: AddMoneyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = payload.idempotency_key or idempotency_key
    txn = wallet_service.add_money(
        db,
        user_id=current_user.id,
        amount=payload.amount,
        funding_method=payload.funding_method,
        idempotency_key=key,
    )
    return TransactionPublic.model_validate(txn)
