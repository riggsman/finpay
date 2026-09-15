from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.transaction import TransactionPublic
from app.schemas.wallet import (
    AddMoneyRequest,
    SendMoneyRequest,
    WalletResponse,
    WithdrawRequest,
)
from app.services import transfers_service, wallet_service

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


@router.post("/send", response_model=TransactionPublic)
def send_money(
    payload: SendMoneyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = payload.idempotency_key or idempotency_key
    txn = transfers_service.send_money(
        db,
        current_user,
        recipient_identifier=payload.recipient,
        amount=payload.amount,
        pin=payload.pin,
        idempotency_key=key,
    )
    return TransactionPublic.model_validate(txn)


@router.post("/withdraw", response_model=TransactionPublic)
def withdraw(
    payload: WithdrawRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = payload.idempotency_key or idempotency_key
    txn = transfers_service.withdraw(
        db,
        current_user,
        amount=payload.amount,
        destination=payload.destination,
        pin=payload.pin,
        idempotency_key=key,
    )
    return TransactionPublic.model_validate(txn)
