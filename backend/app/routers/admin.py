import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, AuthError, ConflictError, NotFoundError, ValidationError
from app.core.ratelimit import check_rate_limit
from app.db.database import get_db
from app.dependencies.admin import get_current_admin
from app.models.catalog import ServiceProvider
from app.models.fees import FeeRule, ServiceFlag
from app.models.kyc import KycProfile, KycStatus
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User
from app.models.wallet import Wallet
from app.notifications import email as email_channel
from app.schemas.limits import LimitIncreaseApprove, LimitIncreaseReject
from app.schemas.support import MessageCreateRequest, TicketStatusUpdate
from app.schemas.admin import (
    AdminKycPublic,
    AdminKycRejectRequest,
    AdminTransactionPublic,
    AdminUserProfile,
    AdminUserSummary,
    EmailTestRequest,
    FeeRulePublic,
    FeeRuleUpdate,
    ProviderCategoryPublic,
    ProviderCreate,
    ProviderPublic,
    ProviderUpdate,
    ServiceFlagPublic,
    ServiceFlagUpdate,
    SettingPublic,
    SettingsUpdate,
)
from app.schemas.auth import LoginRequest, TokenResponse, UserPublic
from app.services import (
    admin_ops_service,
    audit_service,
    auth_service,
    catalog_service,
    fee_service,
    kyc_service,
)

router = APIRouter(prefix="/admin", tags=["back-office"])


@router.post("/login", response_model=TokenResponse)
def admin_login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Separate admin sign-in endpoint. Rejects non-admin accounts."""
    check_rate_limit(
        "admin_login",
        payload.identifier,
        settings.RL_LOGIN_LIMIT,
        settings.RL_LOGIN_WINDOW,
    )
    try:
        user, access, refresh = auth_service.admin_login(
            db, payload.identifier, payload.password
        )
    except AuthError as exc:
        audit_service.record(
            db,
            "ADMIN_LOGIN",
            result="FAILURE",
            meta={"identifier": payload.identifier, "code": exc.code},
        )
        db.commit()
        raise
    audit_service.record(db, "ADMIN_LOGIN", user_id=user.id, result="SUCCESS")
    db.commit()
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_SECONDS,
        user=UserPublic.model_validate(user),
        config=fee_service.get_client_config(db),
    )


def _rule_public(rule: FeeRule) -> FeeRulePublic:
    try:
        cfg = json.loads(rule.config) if rule.config else {}
    except Exception:
        cfg = {}
    return FeeRulePublic(
        operation=rule.operation,
        fee_type=rule.fee_type,
        config=cfg,
        active=rule.active,
    )


def _user_status(user: User) -> str:
    return user.status.value if hasattr(user.status, "value") else str(user.status)


def _kyc_public(kyc: KycProfile, user: User | None = None) -> AdminKycPublic:
    return AdminKycPublic(
        id=kyc.id,
        user_id=kyc.user_id,
        status=kyc.status,
        first_name=kyc.first_name,
        last_name=kyc.last_name,
        date_of_birth=kyc.date_of_birth,
        address_line=kyc.address_line,
        city=kyc.city,
        country=kyc.country,
        id_type=kyc.id_type,
        id_number=kyc.id_number,
        id_document_ref=kyc.id_document_ref,
        id_document_back_ref=kyc.id_document_back_ref,
        selfie_ref=kyc.selfie_ref,
        rejection_reason=kyc.rejection_reason,
        submitted_at=kyc.submitted_at,
        reviewed_at=kyc.reviewed_at,
        user_phone=user.phone if user else None,
        user_email=user.email if user else None,
        user_status=_user_status(user) if user else None,
    )


def _txn_public(
    txn: Transaction, user: User, wallet: Wallet | None, direction: str, db=None
) -> AdminTransactionPublic:
    label = "Money in" if direction == "IN" else "Money out"
    parties = admin_ops_service.resolve_txn_display(db, txn, user)
    status = txn.status.value if hasattr(txn.status, "value") else str(txn.status)
    return AdminTransactionPublic(
        id=txn.id,
        reference=txn.reference,
        user_id=txn.user_id,
        user_phone=user.phone,
        user_name=user.full_name or None,
        account_number=admin_ops_service.account_number_for(wallet.id) if wallet else None,
        type=txn.type,
        direction=direction,
        direction_label=label,
        sender=parties.get("sender"),
        sender_phone=parties.get("sender_phone"),
        receiver=parties.get("receiver"),
        receiver_phone=parties.get("receiver_phone"),
        method=parties.get("method"),
        status=status,
        amount=txn.amount,
        fee=txn.fee,
        currency=txn.currency,
        description=txn.description,
        provider_reference=txn.provider_reference,
        failure_reason=txn.failure_reason,
        pending_reconciliation=bool(txn.pending_reconciliation),
        can_verify_provider=admin_ops_service.can_verify_provider(txn),
        created_at=txn.created_at,
        completed_at=txn.completed_at,
    )


@router.get("/fees", response_model=list[FeeRulePublic])
def list_fees(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return [_rule_public(r) for r in db.query(FeeRule).order_by(FeeRule.operation).all()]


def _validate_fee_config(fee_type: str, config: dict) -> None:
    if fee_type == "FLAT":
        if int(config.get("fee", -1)) < 0:
            raise ValidationError(
                "FLAT fee requires a non-negative 'fee'.", code="INVALID_FEE_CONFIG"
            )
    elif fee_type == "PERCENTAGE":
        if float(config.get("percent", -1)) < 0:
            raise ValidationError(
                "PERCENTAGE fee requires a non-negative 'percent'.",
                code="INVALID_FEE_CONFIG",
            )
    elif fee_type == "TIERED":
        tiers = config.get("tiers")
        if not isinstance(tiers, list) or not tiers:
            raise ValidationError(
                "TIERED fee requires a non-empty 'tiers' list.",
                code="INVALID_FEE_CONFIG",
            )
        for t in tiers:
            if "min" not in t or "fee" not in t:
                raise ValidationError(
                    "Each tier needs 'min' and 'fee'.", code="INVALID_FEE_CONFIG"
                )


@router.put("/fees/{operation}", response_model=FeeRulePublic)
def update_fee(
    operation: str,
    payload: FeeRuleUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    operation = operation.upper()
    # Allow any fee rule that exists (including ones created for new categories).
    rule = db.query(FeeRule).filter(FeeRule.operation == operation).one_or_none()
    if rule is None and operation not in fee_service.FEE_OPERATIONS:
        raise NotFoundError("Unknown operation.", code="UNKNOWN_OPERATION")
    _validate_fee_config(payload.fee_type, payload.config)

    if rule is None:
        rule = FeeRule(operation=operation)
        db.add(rule)
    rule.fee_type = payload.fee_type
    rule.config = json.dumps(payload.config)
    rule.active = payload.active
    audit_service.record(
        db,
        "FEE_RULE_UPDATED",
        user_id=admin.id,
        entity_type="fee_rule",
        entity_id=operation,
        meta={"fee_type": payload.fee_type},
    )
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
    if payload.enabled is None and payload.email_enabled is None:
        raise ValidationError("Provide enabled and/or email_enabled.", code="EMPTY_UPDATE")
    meta = {}
    if payload.enabled is not None:
        flag.enabled = payload.enabled
        meta["enabled"] = payload.enabled
    if payload.email_enabled is not None:
        flag.email_enabled = payload.email_enabled
        meta["email_enabled"] = payload.email_enabled
    audit_service.record(
        db,
        "SERVICE_FLAG_UPDATED",
        user_id=admin.id,
        entity_type="service_flag",
        entity_id=key,
        meta=meta,
    )
    db.commit()
    db.refresh(flag)
    return ServiceFlagPublic(
        key=flag.key,
        label=flag.label,
        kind=flag.kind,
        enabled=flag.enabled,
        email_enabled=flag.email_enabled,
    )


def _provider_public(provider: ServiceProvider) -> ProviderPublic:
    cfg = catalog_service.parse_config(provider.config_json)
    fields = catalog_service.provider_public_fields(provider)
    return ProviderPublic(
        id=provider.id,
        category=provider.category,
        provider_id=provider.provider_id,
        name=provider.name,
        description=provider.description,
        enabled=provider.enabled,
        flow=provider.flow or "direct_topup",
        integration_mode=provider.integration_mode or "MOCK",
        base_url=provider.base_url,
        config=cfg,
        fields=fields,
        target_label=provider.target_label or "Account / phone number",
        icon=provider.icon,
        sort_order=provider.sort_order or 100,
    )


@router.get("/providers", response_model=list[ProviderPublic])
def list_providers(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return [_provider_public(p) for p in catalog_service.list_all_providers(db)]


@router.get("/providers/categories", response_model=list[ProviderCategoryPublic])
def list_provider_categories(
    admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
):
    return [ProviderCategoryPublic(**c) for c in catalog_service.list_categories(db)]


@router.post("/providers", response_model=ProviderPublic)
def create_provider(
    payload: ProviderCreate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    category = catalog_service.normalize_category(payload.category)
    provider_id = catalog_service.normalize_provider_id(payload.provider_id)
    if catalog_service.get_provider(db, category, provider_id):
        raise ConflictError(
            "Provider already exists for this category.", code="PROVIDER_EXISTS"
        )
    provider = catalog_service.create_provider(
        db,
        category=category,
        provider_id=provider_id,
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
        flow=payload.flow,
        integration_mode=payload.integration_mode.upper(),
        base_url=payload.base_url,
        config=payload.config,
        target_label=payload.target_label,
        icon=payload.icon,
        sort_order=payload.sort_order,
    )
    audit_service.record(
        db,
        "PROVIDER_CREATED",
        user_id=admin.id,
        entity_type="provider",
        entity_id=provider.provider_id,
        meta={"category": provider.category, "flow": provider.flow},
    )
    db.commit()
    db.refresh(provider)
    return _provider_public(provider)


@router.put("/providers/{provider_pk}", response_model=ProviderPublic)
def update_provider(
    provider_pk: int,
    payload: ProviderUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    provider = db.get(ServiceProvider, provider_pk)
    if not provider:
        raise NotFoundError("Provider not found.", code="PROVIDER_NOT_FOUND")
    data = payload.model_dump(exclude_unset=True)
    if "integration_mode" in data and data["integration_mode"] is not None:
        data["integration_mode"] = str(data["integration_mode"]).upper()
    catalog_service.update_provider(db, provider, data)
    audit_service.record(
        db,
        "PROVIDER_UPDATED",
        user_id=admin.id,
        entity_type="provider",
        entity_id=provider.provider_id,
        meta={"category": provider.category},
    )
    db.commit()
    db.refresh(provider)
    return _provider_public(provider)


@router.get("/settings", response_model=list[SettingPublic])
def list_settings(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return [SettingPublic(**s) for s in catalog_service.list_settings(db)]


@router.put("/settings")
def update_settings(
    payload: SettingsUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    catalog_service.update_settings(db, payload.values)
    audit_service.record(
        db,
        "SETTINGS_UPDATED",
        user_id=admin.id,
        entity_type="settings",
        meta={"keys": list(payload.values.keys())},
    )
    db.commit()
    return {"updated": list(payload.values.keys())}


@router.post("/email/test")
def email_test(
    payload: EmailTestRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    to = payload.to or admin.email
    if not to:
        raise ValidationError("No recipient email available.", code="NO_RECIPIENT")
    from_name = catalog_service.get_str(db, "email_from_name", "FinPay")
    sent = email_channel.send_email(to, payload.subject, payload.body, from_name)
    return {"sent": sent, "to": to, "backend": settings.EMAIL_BACKEND}


@router.get("/overview")
def overview(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    users = db.query(func.count(User.id)).filter(User.is_admin.is_(False)).scalar()
    txns = db.query(func.count(Transaction.id)).scalar()
    success = (
        db.query(func.count(Transaction.id))
        .filter(Transaction.status == TransactionStatus.SUCCESS.value)
        .scalar()
    )
    volume = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.status == TransactionStatus.SUCCESS.value)
        .scalar()
    )
    fees_collected = (
        db.query(func.coalesce(func.sum(Transaction.fee), 0))
        .filter(Transaction.status == TransactionStatus.SUCCESS.value)
        .scalar()
    )
    pending_kyc = (
        db.query(func.count(KycProfile.id))
        .filter(KycProfile.status == KycStatus.UNDER_REVIEW.value)
        .scalar()
    )
    from app.models.support import SupportTicket

    open_tickets = (
        db.query(func.count(SupportTicket.id))
        .filter(SupportTicket.status.in_(["OPEN", "IN_PROGRESS"]))
        .scalar()
    )
    return {
        "users": int(users or 0),
        "transactions": int(txns or 0),
        "successful_transactions": int(success or 0),
        "processed_volume": int(volume or 0),
        "fees_collected": int(fees_collected or 0),
        "pending_kyc": int(pending_kyc or 0),
        "open_tickets": int(open_tickets or 0),
    }


@router.get("/kyc", response_model=list[AdminKycPublic])
def list_kyc(
    status: str | None = Query(default=None),
    user_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = kyc_service.list_for_admin(
        db, status=status or None, user_id=user_id, limit=limit, offset=offset
    )
    user_ids = {k.user_id for k in rows}
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    return [_kyc_public(k, users.get(k.user_id)) for k in rows]


@router.get("/kyc/{kyc_id}", response_model=AdminKycPublic)
def get_kyc(
    kyc_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    kyc = db.get(KycProfile, kyc_id)
    if not kyc:
        raise NotFoundError("KYC profile not found.", code="KYC_NOT_FOUND")
    user = db.get(User, kyc.user_id)
    return _kyc_public(kyc, user)


@router.get("/kyc/{kyc_id}/media/{ref}")
def get_kyc_media(
    kyc_id: int,
    ref: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Serve a KYC capture for Back Office visual validation."""
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.services import kyc_media

    kyc = db.get(KycProfile, kyc_id)
    if not kyc:
        raise NotFoundError("KYC profile not found.", code="KYC_NOT_FOUND")
    allowed = {
        kyc.id_document_ref,
        kyc.id_document_back_ref,
        kyc.selfie_ref,
    }
    if ref not in allowed:
        raise NotFoundError("Capture not found for this KYC.", code="KYC_CAPTURE_NOT_FOUND")
    path = kyc_media.resolve_path(ref)
    media = (
        "image/jpeg"
        if path.suffix.lower() in (".jpg", ".jpeg")
        else f"image/{path.suffix.lstrip('.')}"
    )
    return FileResponse(path, media_type=media, filename=Path(ref).name)


@router.post("/kyc/{kyc_id}/approve", response_model=AdminKycPublic)
def approve_kyc(
    kyc_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    kyc = kyc_service.admin_approve(db, kyc_id, admin)
    user = db.get(User, kyc.user_id)
    return _kyc_public(kyc, user)


@router.post("/kyc/{kyc_id}/reject", response_model=AdminKycPublic)
def reject_kyc(
    kyc_id: int,
    payload: AdminKycRejectRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    kyc = kyc_service.admin_reject(db, kyc_id, admin, payload.reason)
    user = db.get(User, kyc.user_id)
    return _kyc_public(kyc, user)


@router.get("/users", response_model=list[AdminUserSummary])
def list_users(
    user_id: int | None = None,
    phone: str | None = None,
    name: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    users = admin_ops_service.list_users(
        db, user_id=user_id, phone=phone, name=name, limit=limit, offset=offset
    )
    out: list[AdminUserSummary] = []
    for u in users:
        wallet = db.query(Wallet).filter(Wallet.user_id == u.id).one_or_none()
        kyc = db.query(KycProfile).filter(KycProfile.user_id == u.id).one_or_none()
        out.append(
            AdminUserSummary(
                id=u.id,
                first_name=u.first_name,
                last_name=u.last_name,
                full_name=u.full_name or None,
                email=u.email,
                phone=u.phone,
                status=_user_status(u),
                phone_verified=u.phone_verified,
                email_verified=u.email_verified,
                account_number=(
                    admin_ops_service.account_number_for(wallet.id) if wallet else None
                ),
                kyc_status=kyc.status if kyc else None,
                created_at=u.created_at,
            )
        )
    return out


@router.get("/users/{user_id}", response_model=AdminUserProfile)
def get_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return AdminUserProfile.model_validate(admin_ops_service.get_user_profile(db, user_id))


@router.get("/transactions", response_model=list[AdminTransactionPublic])
def list_transactions(
    user_id: int | None = None,
    phone: str | None = None,
    account_number: str | None = None,
    type: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = admin_ops_service.list_transactions(
        db,
        user_id=user_id,
        phone=phone,
        account_number=account_number,
        type_=type,
        direction=direction,
        status=status,
        limit=limit,
        offset=offset,
    )
    result: list[AdminTransactionPublic] = []
    for txn, user, wallet in rows:
        direction_val = admin_ops_service.ledger_direction_for(db, txn)
        if not direction_val:
            direction_val = admin_ops_service.txn_direction(txn.type)
        result.append(_txn_public(txn, user, wallet, direction_val, db))
    return result


@router.post("/transactions/{transaction_id}/verify-provider")
def verify_transaction_provider(
    transaction_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Query Campay for this FinPay transaction and attempt settlement when terminal."""
    from app.integrations.campay import (
        campay_credentials_ready,
        get_campay_client,
        is_campay_reference,
        map_campay_status,
    )
    from app.services import reconciliation_service

    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise NotFoundError("Transaction not found.", code="TRANSACTION_NOT_FOUND")
    if not campay_credentials_ready():
        raise AppError(
            "Campay is not configured. Set CAMPAY_USERNAME and CAMPAY_PASSWORD.",
            code="CAMPAY_NOT_CONFIGURED",
            status_code=503,
        )
    if not txn.provider_reference or not is_campay_reference(txn.provider_reference):
        raise ValidationError(
            "This transaction has no Campay provider reference to verify.",
            code="NO_PROVIDER_REFERENCE",
        )

    data = get_campay_client().get_transaction(txn.provider_reference)
    mapped = map_campay_status(data.get("status"))
    settled = False
    settle_error = None
    prev_status = reconciliation_service._status_str(txn.status)

    if mapped in ("SUCCESS", "FAILED") and prev_status in reconciliation_service.NON_TERMINAL_STATUSES:
        try:
            settled = bool(
                reconciliation_service.apply_campay_outcome(
                    db,
                    txn,
                    mapped,
                    reason=data.get("reason"),
                    payload=data,
                )
            )
            db.refresh(txn)
        except Exception as exc:  # noqa: BLE001
            settle_error = str(getattr(exc, "message", None) or exc)
            db.rollback()
            txn = db.get(Transaction, transaction_id)
            from app.services import campay_payment_service

            campay_payment_service.apply_status_payload(
                db, data, transaction=txn, notify=False
            )
            db.commit()
            db.refresh(txn)
    else:
        from app.services import campay_payment_service

        campay_payment_service.apply_status_payload(
            db, data, transaction=txn, notify=False
        )
        db.commit()
        db.refresh(txn)

    finpay_status = reconciliation_service._status_str(txn.status)
    action = reconciliation_service.describe_provider_action(mapped, finpay_status, txn.type)
    # If auto-settle claimed success, clear the reconcile CTA.
    if settled:
        action = {
            "needs_reconciliation": False,
            "action_required": (
                f"FinPay was updated to {finpay_status} from Campay {mapped}."
            ),
            "action_label": None,
        }
    elif settle_error and action.get("needs_reconciliation"):
        action = {
            **action,
            "action_required": f"{action['action_required']} (Auto-settle note: {settle_error})",
        }

    user = db.get(User, txn.user_id)
    wallet = (
        db.query(Wallet).filter(Wallet.user_id == txn.user_id).one_or_none()
        if user
        else None
    )
    direction = admin_ops_service.ledger_direction_for(db, txn) or admin_ops_service.txn_direction(
        txn.type
    )
    audit_service.record(
        db,
        "ADMIN_VERIFY_PROVIDER",
        user_id=admin.id,
        entity_type="transaction",
        entity_id=txn.id,
        meta={
            "provider_reference": txn.provider_reference,
            "mapped_status": mapped,
            "previous_status": prev_status,
            "settled": settled,
            "new_status": finpay_status,
            "needs_reconciliation": action["needs_reconciliation"],
            "settle_error": settle_error,
        },
    )
    db.commit()

    return {
        "ok": True,
        "settled": settled,
        "provider_status": data.get("status"),
        "mapped_status": mapped,
        "previous_status": prev_status,
        "finpay_status": finpay_status,
        "needs_reconciliation": action["needs_reconciliation"],
        "action_required": action["action_required"],
        "action_label": action["action_label"],
        "settle_error": settle_error,
        "transaction": _txn_public(txn, user, wallet, direction, db),
        "raw": data,
    }


@router.post("/transactions/{transaction_id}/reconcile")
def reconcile_transaction(
    transaction_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Force-settle a Campay-linked FinPay transaction from the live provider status."""
    from app.services import reconciliation_service

    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise NotFoundError("Transaction not found.", code="TRANSACTION_NOT_FOUND")

    prev_status = reconciliation_service._status_str(txn.status)
    settled, mapped, data = reconciliation_service.admin_reconcile_transaction(db, txn)
    db.refresh(txn)
    finpay_status = reconciliation_service._status_str(txn.status)

    user = db.get(User, txn.user_id)
    wallet = (
        db.query(Wallet).filter(Wallet.user_id == txn.user_id).one_or_none()
        if user
        else None
    )
    direction = admin_ops_service.ledger_direction_for(db, txn) or admin_ops_service.txn_direction(
        txn.type
    )
    audit_service.record(
        db,
        "ADMIN_RECONCILE_TRANSACTION",
        user_id=admin.id,
        entity_type="transaction",
        entity_id=txn.id,
        meta={
            "provider_reference": txn.provider_reference,
            "mapped_status": mapped,
            "previous_status": prev_status,
            "new_status": finpay_status,
            "settled": settled,
        },
    )
    db.commit()

    action = reconciliation_service.describe_provider_action(mapped, finpay_status, txn.type)
    return {
        "ok": True,
        "settled": settled,
        "provider_status": data.get("status"),
        "mapped_status": mapped,
        "previous_status": prev_status,
        "finpay_status": finpay_status,
        "needs_reconciliation": False,
        "action_required": (
            f"Reconciled successfully. FinPay is now {finpay_status}."
            if settled
            else action["action_required"]
        ),
        "action_label": None,
        "transaction": _txn_public(txn, user, wallet, direction, db),
        "raw": data,
    }


@router.get("/limit-requests")
def list_limit_requests(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from app.services import limit_service

    rows = limit_service.list_for_admin(db, status=status, limit=limit, offset=offset)
    out = []
    for row in rows:
        user = db.get(User, row.user_id)
        out.append({
            "id": row.id,
            "user_id": row.user_id,
            "user_name": (user.full_name if user else None) or (user.phone if user else None),
            "user_phone": user.phone if user else None,
            "requested_per_txn_limit": row.requested_per_txn_limit,
            "requested_daily_limit": row.requested_daily_limit,
            "reason": row.reason,
            "status": row.status,
            "rejection_reason": row.rejection_reason,
            "approved_per_txn_limit": row.approved_per_txn_limit,
            "approved_daily_limit": row.approved_daily_limit,
            "duration_days": row.duration_days,
            "spending_cap": row.spending_cap,
            "amount_spent": row.amount_spent,
            "starts_at": row.starts_at,
            "expires_at": row.expires_at,
            "reviewed_at": row.reviewed_at,
            "created_at": row.created_at,
        })
    return out


@router.post("/limit-requests/{request_id}/approve")
def approve_limit_request(
    request_id: int,
    payload: LimitIncreaseApprove | None = None,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from app.services import limit_service

    body = payload or LimitIncreaseApprove()
    row = limit_service.approve(
        db,
        request_id,
        admin,
        approved_per_txn_limit=body.approved_per_txn_limit,
        approved_daily_limit=body.approved_daily_limit,
        duration_days=body.duration_days,
        spending_cap=body.spending_cap,
    )
    return {"id": row.id, "status": row.status, "expires_at": row.expires_at}


@router.post("/limit-requests/{request_id}/reject")
def reject_limit_request(
    request_id: int,
    payload: LimitIncreaseReject | None = None,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from app.services import limit_service

    body = payload or LimitIncreaseReject()
    row = limit_service.reject(db, request_id, admin, reason=body.reason)
    return {"id": row.id, "status": row.status, "rejection_reason": row.rejection_reason}


@router.get("/tickets")
def list_support_tickets(
    status: str | None = None,
    user_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from app.services import support_service

    rows = support_service.list_tickets_admin(
        db, status=status, user_id=user_id, limit=limit, offset=offset
    )
    user_ids = {t.user_id for t in rows}
    users = (
        {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    return [
        support_service.ticket_to_admin_public(t, users.get(t.user_id)) for t in rows
    ]


@router.get("/tickets/{ticket_id}")
def get_support_ticket(
    ticket_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from app.services import support_service

    ticket, messages, user = support_service.get_ticket_admin(db, ticket_id)
    data = support_service.ticket_to_admin_public(ticket, user)
    data["messages"] = [
        {
            "id": m.id,
            "sender": m.sender,
            "body": m.body,
            "created_at": m.created_at,
        }
        for m in messages
    ]
    return data


@router.get("/tickets/{ticket_id}/screenshot")
def get_support_ticket_screenshot(
    ticket_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.services import support_service

    path = support_service.get_ticket_screenshot_admin(db, ticket_id)
    media = (
        "image/jpeg"
        if path.suffix.lower() in (".jpg", ".jpeg")
        else f"image/{path.suffix.lstrip('.')}"
    )
    return FileResponse(path, media_type=media, filename=Path(path).name)


@router.post("/tickets/{ticket_id}/messages")
def reply_support_ticket(
    ticket_id: int,
    payload: MessageCreateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from app.services import support_service

    msg = support_service.admin_reply(db, admin, ticket_id, payload.body)
    return {
        "id": msg.id,
        "sender": msg.sender,
        "body": msg.body,
        "created_at": msg.created_at,
    }


@router.post("/tickets/{ticket_id}/status")
def update_support_ticket_status(
    ticket_id: int,
    payload: TicketStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    from app.services import support_service

    ticket = support_service.admin_update_status(db, ticket_id, payload.status)
    return support_service.ticket_to_public(ticket)

