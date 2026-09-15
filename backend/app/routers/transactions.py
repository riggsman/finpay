from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.transaction import Transaction, TransactionEvent
from app.models.user import User
from app.schemas.transaction import TransactionEventPublic, TransactionPublic

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionPublic])
def list_transactions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    type: str | None = None,
):
    q = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    if status:
        q = q.filter(Transaction.status == status)
    if type:
        q = q.filter(Transaction.type == type)
    rows = q.order_by(Transaction.created_at.desc()).limit(limit).all()
    return [TransactionPublic.model_validate(r) for r in rows]


@router.get("/{transaction_id}", response_model=TransactionPublic)
def get_transaction(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.user_id != current_user.id:
        raise NotFoundError("Transaction not found.", code="TRANSACTION_NOT_FOUND")
    return TransactionPublic.model_validate(txn)


@router.get("/{transaction_id}/events", response_model=list[TransactionEventPublic])
def get_transaction_events(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.user_id != current_user.id:
        raise NotFoundError("Transaction not found.", code="TRANSACTION_NOT_FOUND")
    rows = (
        db.query(TransactionEvent)
        .filter(TransactionEvent.transaction_id == transaction_id)
        .order_by(TransactionEvent.created_at.asc())
        .all()
    )
    return [TransactionEventPublic.model_validate(r) for r in rows]
