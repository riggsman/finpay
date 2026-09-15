import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
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
    page: int = Query(default=1, ge=1),
    status: str | None = None,
    type: str | None = None,
    date_from: dt.datetime | None = None,
    date_to: dt.datetime | None = None,
    amount_min: int | None = Query(default=None, ge=0),
    amount_max: int | None = Query(default=None, ge=0),
    search: str | None = None,
):
    q = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    if status:
        q = q.filter(Transaction.status == status)
    if type:
        q = q.filter(Transaction.type == type)
    if date_from:
        q = q.filter(Transaction.created_at >= date_from)
    if date_to:
        q = q.filter(Transaction.created_at <= date_to)
    if amount_min is not None:
        q = q.filter(Transaction.amount >= amount_min)
    if amount_max is not None:
        q = q.filter(Transaction.amount <= amount_max)
    if search:
        like = f"%{search}%"
        q = q.filter(
            or_(Transaction.reference.ilike(like), Transaction.description.ilike(like))
        )
    rows = (
        q.order_by(Transaction.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
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


@router.get("/{transaction_id}/receipt")
def get_receipt(
    transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txn = db.get(Transaction, transaction_id)
    if not txn or txn.user_id != current_user.id:
        raise NotFoundError("Transaction not found.", code="TRANSACTION_NOT_FOUND")
    if txn.status != "SUCCESS":
        raise NotFoundError("Receipt is only available for successful transactions.",
                            code="RECEIPT_UNAVAILABLE")

    from app.models.billing import BillPayment

    bill = (
        db.query(BillPayment)
        .filter(BillPayment.transaction_id == txn.id)
        .one_or_none()
    )
    receipt = {
        "receipt_number": f"RCP-{txn.reference.upper()}",
        "transaction_id": txn.id,
        "reference": txn.reference,
        "type": txn.type,
        "amount": txn.amount,
        "fee": txn.fee,
        "total": txn.total,
        "currency": txn.currency,
        "status": txn.status,
        "provider_reference": txn.provider_reference,
        "created_at": txn.created_at,
        "completed_at": txn.completed_at,
    }
    if bill:
        receipt.update(
            {
                "provider": bill.provider_id,
                "meter_number": bill.meter_number,
                "customer": bill.customer_name,
                "service": bill.category,
            }
        )
    return receipt


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
