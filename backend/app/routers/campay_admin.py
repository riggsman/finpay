"""Campay webhook + admin test endpoints."""

from __future__ import annotations

import hashlib
import hmac
import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette import status

from app.core.config import settings
from app.core.exceptions import AppError, ValidationError
from app.db.database import get_db
from app.dependencies.admin import get_current_admin
from app.integrations.campay import (
    CampayError,
    campay_configured,
    campay_credentials_ready,
    get_campay_client,
    map_campay_status,
    normalize_msisdn,
    reset_campay_client,
)
from app.models.user import User
from app.services import audit_service, reconciliation_service

router = APIRouter(tags=["campay"])
admin_router = APIRouter(prefix="/admin/campay", tags=["admin-campay"])
webhook_router = APIRouter(prefix="/webhooks/campay", tags=["webhooks"])


def _require_campay():
    # Sandbox / diagnostics need credentials only — not PAYMENT_MODE=live —
    # so operators can verify Campay without enabling live wallet MoMo.
    if not campay_credentials_ready():
        raise AppError(
            "Campay is not configured. Set CAMPAY_USERNAME and CAMPAY_PASSWORD.",
            code="CAMPAY_NOT_CONFIGURED",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _mask_username(username: str) -> str:
    u = (username or "").strip()
    if not u:
        return ""
    if len(u) <= 4:
        return "*" * len(u)
    return u[:2] + ("*" * (len(u) - 4)) + u[-2:]


class CampayTestAmountBody(BaseModel):
    phone: str = Field(min_length=8, max_length=40)
    amount: int = Field(gt=0, description="Amount in whole XAF francs")


@admin_router.get("/status")
def campay_status(admin: User = Depends(get_current_admin)):
    creds = campay_credentials_ready()
    return {
        "configured": creds,
        "credentials_ready": creds,
        "payment_mode": settings.payment_mode,
        "payments_live": settings.payments_live,
        "wallet_campay_enabled": campay_configured(),
        "reconcile_worker_enabled": bool(settings.RECONCILE_WORKER_ENABLED),
        "reconcile_interval_seconds": float(settings.RECONCILE_INTERVAL_SECONDS),
        "base_url": (settings.CAMPAY_BASE_URL or "").rstrip("/"),
        "username_masked": _mask_username(settings.CAMPAY_USERNAME) if creds else "",
        "webhook_configured": bool((settings.CAMPAY_WEBHOOK_KEY or "").strip()),
    }


@admin_router.get("/balance")
def campay_balance(admin: User = Depends(get_current_admin)):
    _require_campay()
    return get_campay_client().get_balance()


@admin_router.get("/holder-info")
def campay_holder_info(
    phone: str = Query(..., min_length=8),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _require_campay()
    from app.services.name_resolution_service import resolve_phone_name

    return resolve_phone_name(db, phone)


@admin_router.post("/test/token")
def campay_test_token(admin: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    _require_campay()
    reset_campay_client()
    try:
        token = get_campay_client().get_token(force=True)
    except CampayError as exc:
        raise
    audit_service.record(
        db,
        "CAMPAY_TEST_TOKEN",
        user_id=admin.id,
        entity_type="campay",
        entity_id="token",
        meta={"ok": True},
    )
    db.commit()
    return {"ok": True, "token_preview": f"{token[:8]}…" if token else None}


@admin_router.post("/test/collect")
def campay_test_collect(
    payload: CampayTestAmountBody,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _require_campay()
    from app.services import campay_payment_service

    ext = f"admin-test-collect-{uuid.uuid4().hex[:12]}"
    result = get_campay_client().collect(
        amount_xaf=int(payload.amount),
        phone=payload.phone,
        description="FinPay admin Campay collect test",
        external_reference=ext,
    )
    ref = str(result.get("reference") or "").strip()
    if ref:
        campay_payment_service.record_initiate(
            db,
            reference=ref,
            endpoint="collect",
            user_id=admin.id,
            transaction_id=None,
            external_reference=ext,
            phone_number=payload.phone,
            amount_minor=int(payload.amount) * 100,
            currency="XAF",
            operator=result.get("operator"),
            raw=result,
        )
        campay_payment_service.apply_status_payload(
            db, {**result, "external_reference": ext, "endpoint": "collect"},
            user_id=admin.id,
            endpoint="collect",
            notify=False,
        )
    audit_service.record(
        db,
        "CAMPAY_TEST_COLLECT",
        user_id=admin.id,
        entity_type="campay",
        entity_id=str(result.get("reference") or ext),
        meta={"amount": payload.amount, "phone": normalize_msisdn(payload.phone), "external_reference": ext},
    )
    db.commit()
    return {
        "ok": True,
        "external_reference": ext,
        "reference": result.get("reference"),
        "status": result.get("status") or "PENDING",
        "ussd_code": result.get("ussd_code"),
        "operator": result.get("operator"),
        "raw": result,
        "note": "Live Campay call; does not credit FinPay wallets. Status updates persist to campay_payments.",
    }


@admin_router.post("/test/withdraw")
def campay_test_withdraw(
    payload: CampayTestAmountBody,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _require_campay()
    from app.services import campay_payment_service

    ext = f"admin-test-withdraw-{uuid.uuid4().hex[:12]}"
    result = get_campay_client().withdraw(
        amount_xaf=int(payload.amount),
        phone=payload.phone,
        description="FinPay admin Campay withdraw test",
        external_reference=ext,
    )
    ref = str(result.get("reference") or "").strip()
    if ref:
        campay_payment_service.record_initiate(
            db,
            reference=ref,
            endpoint="withdraw",
            user_id=admin.id,
            transaction_id=None,
            external_reference=ext,
            phone_number=payload.phone,
            amount_minor=int(payload.amount) * 100,
            currency="XAF",
            operator=result.get("operator"),
            raw=result,
        )
        campay_payment_service.apply_status_payload(
            db, {**result, "external_reference": ext, "endpoint": "withdraw"},
            user_id=admin.id,
            endpoint="withdraw",
            notify=False,
        )
    audit_service.record(
        db,
        "CAMPAY_TEST_WITHDRAW",
        user_id=admin.id,
        entity_type="campay",
        entity_id=str(result.get("reference") or ext),
        meta={"amount": payload.amount, "phone": normalize_msisdn(payload.phone), "external_reference": ext},
    )
    db.commit()
    return {
        "ok": True,
        "external_reference": ext,
        "reference": result.get("reference"),
        "status": result.get("status") or "PENDING",
        "raw": result,
        "note": "Live Campay call; does not debit FinPay wallets. Status updates persist to campay_payments.",
    }


@admin_router.get("/test/transaction/{reference}")
def campay_test_transaction(
    reference: str,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    _require_campay()
    from app.models.transaction import Transaction
    from app.services import campay_payment_service

    data = get_campay_client().get_transaction(reference)
    payment = campay_payment_service.apply_status_payload(
        db, data, user_id=admin.id, notify=False
    )
    mapped = map_campay_status(data.get("status"))
    txn = None
    if payment and payment.transaction_id:
        txn = db.get(Transaction, payment.transaction_id)

    if txn and mapped in ("SUCCESS", "FAILED") and txn.status in ("PENDING", "PROCESSING"):
        reconciliation_service.apply_campay_outcome(
            db, txn, mapped, reason=(payment.reason if payment else None), payload=data
        )
    elif payment and mapped in ("SUCCESS", "FAILED"):
        campay_payment_service.notify_parties(db, payment, transaction=txn)
        db.commit()
    else:
        db.commit()

    payment = campay_payment_service.get_by_reference(db, reference) or payment
    return {
        "reference": data.get("reference") or reference,
        "status": data.get("status"),
        "mapped_status": mapped,
        "persisted": {
            "reference": payment.reference if payment else None,
            "status": payment.status if payment else None,
            "amount": payment.amount if payment else None,
            "currency": payment.currency if payment else None,
            "operator": payment.operator if payment else None,
            "operator_reference": payment.operator_reference if payment else None,
            "external_reference": payment.external_reference if payment else None,
            "phone_number": payment.phone_number if payment else None,
            "reason": payment.reason if payment else None,
            "transaction_id": payment.transaction_id if payment else None,
            "finalized_at": payment.finalized_at.isoformat() if payment and payment.finalized_at else None,
            "notified_at": payment.notified_at.isoformat() if payment and payment.notified_at else None,
        } if payment else None,
        "raw": data,
    }


def _verify_webhook_signature(request: Request, signature: str | None) -> None:
    key = (settings.CAMPAY_WEBHOOK_KEY or "").strip()
    if not key:
        return
    if not signature:
        raise ValidationError("Missing webhook signature.", code="INVALID_SIGNATURE")
    # Accept either plain shared-secret equality or HMAC of query string.
    if hmac.compare_digest(signature, key):
        return
    payload = request.url.query.encode("utf-8")
    digest = hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    if hmac.compare_digest(signature, digest):
        return
    raise ValidationError("Invalid webhook signature.", code="INVALID_SIGNATURE")


@webhook_router.api_route("", methods=["GET", "POST"])
@webhook_router.api_route("/", methods=["GET", "POST"])
async def campay_webhook(request: Request, db: Session = Depends(get_db)):
    """Campay payment status callback (idempotent settle)."""
    params = dict(request.query_params)
    body: dict = {}
    if request.method == "POST":
        try:
            raw = await request.json()
            if isinstance(raw, dict):
                body = raw
        except Exception:
            body = {}
    data = {**body, **params}

    signature = data.get("signature") or request.headers.get("X-Campay-Signature")
    _verify_webhook_signature(request, signature)

    campay_ref = (
        data.get("reference")
        or data.get("transaction_reference")
        or data.get("campay_reference")
    )
    external = data.get("external_reference")
    status_raw = data.get("status") or data.get("payment_status")
    outcome = map_campay_status(status_raw)

    txn = reconciliation_service.find_txn_for_campay(
        db,
        campay_reference=str(campay_ref) if campay_ref else None,
        external_reference=str(external) if external else None,
    )

    from app.services import campay_payment_service

    # Always persist Campay fields from the webhook payload.
    payment = campay_payment_service.apply_status_payload(
        db, data, transaction=txn, notify=False
    )

    if not txn:
        # Admin/sandbox (or unknown) payments without a FinPay wallet txn.
        # Always ACK so Campay does not retry-storm; notify only on final status.
        if payment and outcome in ("SUCCESS", "FAILED"):
            campay_payment_service.notify_parties(db, payment, transaction=None)
        db.commit()
        return {
            "ok": True,
            "campay_reference": (payment.reference if payment else campay_ref),
            "status": (
                payment.mapped_status
                if payment
                else (outcome or "PENDING")
            ),
            "wallet_txn": False,
        }

    if txn.status in ("SUCCESS", "FAILED"):
        if payment:
            campay_payment_service.notify_parties(db, payment, transaction=txn)
            db.commit()
        return {"ok": True, "transaction_id": txn.id, "status": txn.status, "already_settled": True}

    if outcome == "PENDING":
        db.commit()
        return {"ok": True, "transaction_id": txn.id, "status": txn.status, "pending": True}

    reason = data.get("reason") or data.get("failure_reason")
    reconciliation_service.apply_campay_outcome(
        db, txn, outcome, reason=reason, payload=data
    )
    db.refresh(txn)
    return {"ok": True, "transaction_id": txn.id, "status": txn.status}
