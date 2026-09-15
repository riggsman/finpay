import json

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.db.database import get_db
from app.dependencies.admin import get_current_admin
from app.models.fees import FeeRule, ServiceFlag
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User
from app.schemas.admin import (
    FeeRulePublic,
    FeeRuleUpdate,
    ServiceFlagPublic,
    ServiceFlagUpdate,
)
from app.services import audit_service, fee_service

router = APIRouter(prefix="/admin", tags=["back-office"])


def _rule_public(rule: FeeRule) -> FeeRulePublic:
    try:
        cfg = json.loads(rule.config) if rule.config else {}
    except Exception:
        cfg = {}
    return FeeRulePublic(operation=rule.operation, fee_type=rule.fee_type,
                         config=cfg, active=rule.active)


@router.get("/fees", response_model=list[FeeRulePublic])
def list_fees(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return [_rule_public(r) for r in db.query(FeeRule).order_by(FeeRule.operation).all()]


def _validate_fee_config(fee_type: str, config: dict) -> None:
    if fee_type == "FLAT":
        if int(config.get("fee", -1)) < 0:
            raise ValidationError("FLAT fee requires a non-negative 'fee'.",
                                  code="INVALID_FEE_CONFIG")
    elif fee_type == "PERCENTAGE":
        if float(config.get("percent", -1)) < 0:
            raise ValidationError("PERCENTAGE fee requires a non-negative 'percent'.",
                                  code="INVALID_FEE_CONFIG")
    elif fee_type == "TIERED":
        tiers = config.get("tiers")
        if not isinstance(tiers, list) or not tiers:
            raise ValidationError("TIERED fee requires a non-empty 'tiers' list.",
                                  code="INVALID_FEE_CONFIG")
        for t in tiers:
            if "min" not in t or "fee" not in t:
                raise ValidationError("Each tier needs 'min' and 'fee'.",
                                      code="INVALID_FEE_CONFIG")


@router.put("/fees/{operation}", response_model=FeeRulePublic)
def update_fee(
    operation: str,
    payload: FeeRuleUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    operation = operation.upper()
    if operation not in fee_service.FEE_OPERATIONS:
        raise NotFoundError("Unknown operation.", code="UNKNOWN_OPERATION")
    _validate_fee_config(payload.fee_type, payload.config)

    rule = db.query(FeeRule).filter(FeeRule.operation == operation).one_or_none()
    if rule is None:
        rule = FeeRule(operation=operation)
        db.add(rule)
    rule.fee_type = payload.fee_type
    rule.config = json.dumps(payload.config)
    rule.active = payload.active
    audit_service.record(db, "FEE_RULE_UPDATED", user_id=admin.id, entity_type="fee_rule",
                         entity_id=operation, meta={"fee_type": payload.fee_type})
    db.commit()
    db.refresh(rule)
    return _rule_public(rule)


@router.get("/services", response_model=list[ServiceFlagPublic])
def list_services(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return [ServiceFlagPublic(**f) for f in fee_service.get_service_flags(db)]


@router.put("/services/{key}", response_model=ServiceFlagPublic)
def update_service(
    key: str,
    payload: ServiceFlagUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    flag = db.query(ServiceFlag).filter(ServiceFlag.key == key).one_or_none()
    if flag is None:
        raise NotFoundError("Unknown service.", code="UNKNOWN_SERVICE")
    flag.enabled = payload.enabled
    audit_service.record(db, "SERVICE_FLAG_UPDATED", user_id=admin.id,
                         entity_type="service_flag", entity_id=key,
                         meta={"enabled": payload.enabled})
    db.commit()
    db.refresh(flag)
    return ServiceFlagPublic(key=flag.key, label=flag.label, kind=flag.kind,
                             enabled=flag.enabled)


@router.get("/overview")
def overview(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(func.count(User.id)).scalar()
    txns = db.query(func.count(Transaction.id)).scalar()
    success = db.query(func.count(Transaction.id)).filter(
        Transaction.status == TransactionStatus.SUCCESS.value
    ).scalar()
    volume = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.status == TransactionStatus.SUCCESS.value
    ).scalar()
    fees_collected = db.query(func.coalesce(func.sum(Transaction.fee), 0)).filter(
        Transaction.status == TransactionStatus.SUCCESS.value
    ).scalar()
    return {
        "users": int(users or 0),
        "transactions": int(txns or 0),
        "successful_transactions": int(success or 0),
        "processed_volume": int(volume or 0),
        "fees_collected": int(fees_collected or 0),
    }
