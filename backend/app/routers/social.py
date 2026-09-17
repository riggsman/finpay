from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.social import (
    BeneficiaryCreateRequest,
    BeneficiaryPublic,
    MoneyRequestCreate,
    MoneyRequestPublic,
    PayRequestBody,
)
from app.services import social_service

router = APIRouter(tags=["social"])


def _public(db: Session, req) -> MoneyRequestPublic:
    return MoneyRequestPublic.model_validate(social_service.serialize_money_request(db, req))


# --- Beneficiaries ---------------------------------------------------------

@router.post("/beneficiaries", response_model=BeneficiaryPublic)
def add_beneficiary(
    payload: BeneficiaryCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ben = social_service.add_beneficiary(db, current_user, payload.identifier)
    db.commit()
    return BeneficiaryPublic.model_validate(ben)


@router.get("/beneficiaries", response_model=list[BeneficiaryPublic])
def list_beneficiaries(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return [BeneficiaryPublic.model_validate(b) for b in
            social_service.list_beneficiaries(db, current_user)]


@router.delete("/beneficiaries/{beneficiary_id}")
def delete_beneficiary(
    beneficiary_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    social_service.delete_beneficiary(db, current_user, beneficiary_id)
    db.commit()
    return {"deleted": True}


# --- Money requests --------------------------------------------------------

@router.post("/money-requests", response_model=MoneyRequestPublic)
def create_request(
    payload: MoneyRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = social_service.create_request(
        db, current_user, payload.payer, payload.amount, payload.note
    )
    return _public(db, req)


@router.get("/money-requests", response_model=list[MoneyRequestPublic])
def list_requests(
    direction: str = Query(default="all", pattern="^(all|incoming|outgoing)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [
        _public(db, r)
        for r in social_service.list_requests(db, current_user, direction)
    ]


@router.post("/money-requests/{request_id}/pay", response_model=MoneyRequestPublic)
def pay_request(
    request_id: int,
    payload: PayRequestBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = social_service.pay_request(
        db, current_user, request_id, payload.pin, payload.phone
    )
    return _public(db, req)


@router.post("/money-requests/{request_id}/decline", response_model=MoneyRequestPublic)
def decline_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = social_service.decline_request(db, current_user, request_id)
    return _public(db, req)


@router.post("/money-requests/{request_id}/cancel", response_model=MoneyRequestPublic)
def cancel_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    req = social_service.cancel_request(db, current_user, request_id)
    return _public(db, req)
