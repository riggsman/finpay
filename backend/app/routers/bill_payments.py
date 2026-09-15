from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.billing import (
    ElectricityConfirmRequest,
    MeterValidateRequest,
    MeterValidateResponse,
    TopupConfirmRequest,
)
from app.schemas.transaction import TransactionPublic
from app.services import billing_service

router = APIRouter(prefix="/bill-payments", tags=["bill-payments"])


@router.get("/providers")
def list_providers(
    category: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"providers": billing_service.list_providers(db, category)}


@router.post("/electricity/validate", response_model=MeterValidateResponse)
def validate_meter(
    payload: MeterValidateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    validation = billing_service.validate_meter(
        db, current_user, payload.provider_id, payload.meter_number
    )
    pname = billing_service.provider_name(db, "electricity", validation.provider_id)
    return MeterValidateResponse(
        validation_token=validation.token,
        customer={"name": validation.customer_name, "meter_number": validation.meter_number},
        provider={"id": validation.provider_id, "name": pname},
        expires_in=settings.VALIDATION_TOKEN_TTL_SECONDS,
    )


@router.get("/topup/providers")
def list_topup_providers(
    category: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"providers": billing_service.list_topup_providers(db, category)}


@router.post("/topup/confirm", response_model=TransactionPublic)
def confirm_topup(
    payload: TopupConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = payload.idempotency_key or idempotency_key
    txn = billing_service.confirm_topup(
        db, current_user, payload.category, payload.provider_id, payload.target,
        payload.amount, payload.pin, key,
    )
    return TransactionPublic.model_validate(txn)


@router.post("/electricity/confirm", response_model=TransactionPublic)
def confirm_electricity(
    payload: ElectricityConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = payload.idempotency_key or idempotency_key
    txn = billing_service.confirm_electricity(
        db,
        current_user,
        validation_token=payload.validation_token,
        amount=payload.amount,
        pin=payload.pin,
        idempotency_key=key,
    )
    return TransactionPublic.model_validate(txn)
