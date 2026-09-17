import datetime as dt

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.limits import LimitIncreaseRequest, LimitIncreaseStatus
from app.models.user import User
from app.services import audit_service, catalog_service
from app.services.notification_service import create_notification, deliver_notification
from app.websocket.socket import emit_to_user


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _money(minor: int) -> str:
    return f"{minor / 100:,.2f}"


def _deliver_limit_decision(notif, *, event_type: str, payload: dict) -> None:
    """Push the limit decision over Socket.IO, FCM, and email channels."""
    deliver_notification(notif)
    emit_to_user(
        notif.user_id,
        event_type,
        {
            "title": notif.title,
            "message": notif.message,
            "notification_id": notif.id,
            "type": notif.type,
            "priority": notif.priority,
            **payload,
        },
        event_id=notif.event_id,
    )

def refresh_expired_grants(db: Session, user_id: int | None = None) -> None:
    """Mark approved grants past expires_at as EXPIRED and revert user limits."""
    now = _now()
    q = db.query(LimitIncreaseRequest).filter(
        LimitIncreaseRequest.status == LimitIncreaseStatus.APPROVED.value,
        LimitIncreaseRequest.expires_at.isnot(None),
        LimitIncreaseRequest.expires_at <= now,
    )
    if user_id is not None:
        q = q.filter(LimitIncreaseRequest.user_id == user_id)
    rows = q.all()
    for row in rows:
        row.status = LimitIncreaseStatus.EXPIRED.value
        user = db.get(User, row.user_id)
        if user:
            per, daily = catalog_service.default_limits(db)
            user.per_txn_limit = per
            user.daily_limit = daily
    if rows:
        db.flush()


def active_grant(db: Session, user_id: int) -> LimitIncreaseRequest | None:
    refresh_expired_grants(db, user_id)
    now = _now()
    rows = (
        db.query(LimitIncreaseRequest)
        .filter(
            LimitIncreaseRequest.user_id == user_id,
            LimitIncreaseRequest.status == LimitIncreaseStatus.APPROVED.value,
        )
        .order_by(LimitIncreaseRequest.id.desc())
        .all()
    )
    for row in rows:
        if row.expires_at and row.expires_at <= now:
            row.status = LimitIncreaseStatus.EXPIRED.value
            continue
        if row.spending_cap is not None and row.amount_spent >= row.spending_cap:
            row.status = LimitIncreaseStatus.EXHAUSTED.value
            user = db.get(User, user_id)
            if user:
                per, daily = catalog_service.default_limits(db)
                user.per_txn_limit = per
                user.daily_limit = daily
            db.flush()
            continue
        return row
    return None


def effective_limits(db: Session, user: User) -> tuple[int, int]:
    """Resolve limits: active admin-approved grant, else platform defaults."""
    grant = active_grant(db, user.id)
    if grant and grant.approved_per_txn_limit and grant.approved_daily_limit:
        return int(grant.approved_per_txn_limit), int(grant.approved_daily_limit)
    return catalog_service.default_limits(db)


def apply_defaults_to_user(db: Session, user: User) -> None:
    per, daily = catalog_service.default_limits(db)
    user.per_txn_limit = per
    user.daily_limit = daily


def limits_snapshot(db: Session, user: User) -> dict:
    from app.services import security_service

    per, daily = effective_limits(db, user)
    grant = active_grant(db, user.id)
    spent_today = security_service.spent_today(db, user.id)
    remaining_daily = max(0, daily - spent_today)
    remaining_grant = None
    if grant and grant.spending_cap is not None:
        remaining_grant = max(0, int(grant.spending_cap) - int(grant.amount_spent or 0))
    return {
        "per_txn_limit": per,
        "daily_limit": daily,
        "spent_today": spent_today,
        "remaining_daily": remaining_daily,
        "default_per_txn_limit": catalog_service.default_limits(db)[0],
        "default_daily_limit": catalog_service.default_limits(db)[1],
        "active_grant": (
            {
                "id": grant.id,
                "per_txn_limit": grant.approved_per_txn_limit,
                "daily_limit": grant.approved_daily_limit,
                "expires_at": grant.expires_at,
                "spending_cap": grant.spending_cap,
                "amount_spent": grant.amount_spent,
                "remaining_allowance": remaining_grant,
            }
            if grant
            else None
        ),
    }


def create_request(
    db: Session,
    user: User,
    *,
    requested_per_txn_limit: int,
    requested_daily_limit: int,
    reason: str | None,
) -> LimitIncreaseRequest:
    default_per, default_daily = catalog_service.default_limits(db)
    if requested_per_txn_limit <= default_per and requested_daily_limit <= default_daily:
        raise ValidationError(
            "Requested limits must be higher than your current default limits.",
            code="LIMIT_REQUEST_TOO_LOW",
        )
    pending = (
        db.query(LimitIncreaseRequest)
        .filter(
            LimitIncreaseRequest.user_id == user.id,
            LimitIncreaseRequest.status == LimitIncreaseStatus.PENDING.value,
        )
        .one_or_none()
    )
    if pending:
        raise ConflictError(
            "You already have a pending limit increase request.",
            code="LIMIT_REQUEST_PENDING",
        )
    if active_grant(db, user.id):
        raise ConflictError(
            "You already have an active raised limit. Wait until it expires or is fully used.",
            code="LIMIT_GRANT_ACTIVE",
        )

    row = LimitIncreaseRequest(
        user_id=user.id,
        requested_per_txn_limit=requested_per_txn_limit,
        requested_daily_limit=requested_daily_limit,
        reason=(reason or "").strip() or None,
        status=LimitIncreaseStatus.PENDING.value,
    )
    db.add(row)
    db.flush()
    audit_service.record(
        db,
        "LIMIT_INCREASE_REQUESTED",
        user_id=user.id,
        entity_type="limit_increase_request",
        entity_id=row.id,
        meta={
            "per_txn": requested_per_txn_limit,
            "daily": requested_daily_limit,
        },
    )
    db.commit()
    db.refresh(row)
    return row


def list_for_user(db: Session, user_id: int, limit: int = 20) -> list[LimitIncreaseRequest]:
    return (
        db.query(LimitIncreaseRequest)
        .filter(LimitIncreaseRequest.user_id == user_id)
        .order_by(LimitIncreaseRequest.id.desc())
        .limit(limit)
        .all()
    )


def list_for_admin(
    db: Session, *, status: str | None = None, limit: int = 100, offset: int = 0
) -> list[LimitIncreaseRequest]:
    refresh_expired_grants(db)
    q = db.query(LimitIncreaseRequest)
    if status:
        q = q.filter(LimitIncreaseRequest.status == status.upper())
    return q.order_by(LimitIncreaseRequest.id.desc()).offset(offset).limit(limit).all()


def approve(
    db: Session,
    request_id: int,
    admin: User,
    *,
    approved_per_txn_limit: int | None = None,
    approved_daily_limit: int | None = None,
    duration_days: int = 30,
    spending_cap: int | None = None,
) -> LimitIncreaseRequest:
    row = db.get(LimitIncreaseRequest, request_id)
    if not row:
        raise NotFoundError("Limit increase request not found.", code="LIMIT_REQUEST_NOT_FOUND")
    if row.status != LimitIncreaseStatus.PENDING.value:
        raise ConflictError("Only pending requests can be approved.", code="LIMIT_REQUEST_NOT_PENDING")
    if duration_days < 1 or duration_days > 365:
        raise ValidationError("Duration must be between 1 and 365 days.", code="INVALID_DURATION")

    per = int(approved_per_txn_limit or row.requested_per_txn_limit)
    daily = int(approved_daily_limit or row.requested_daily_limit)
    default_per, default_daily = catalog_service.default_limits(db)
    if per <= default_per and daily <= default_daily:
        raise ValidationError(
            "Approved limits must exceed the platform default limits.",
            code="LIMIT_APPROVAL_TOO_LOW",
        )
    if spending_cap is not None and spending_cap <= 0:
        raise ValidationError("Spending cap must be positive when set.", code="INVALID_SPENDING_CAP")

    # Close any prior approved grant for this user.
    prior = active_grant(db, row.user_id)
    if prior and prior.id != row.id:
        prior.status = LimitIncreaseStatus.EXPIRED.value

    now = _now()
    row.status = LimitIncreaseStatus.APPROVED.value
    row.approved_per_txn_limit = per
    row.approved_daily_limit = daily
    row.duration_days = duration_days
    row.spending_cap = spending_cap
    row.amount_spent = 0
    row.starts_at = now
    row.expires_at = now + dt.timedelta(days=duration_days)
    row.reviewed_by_admin_id = admin.id
    row.reviewed_at = now
    row.rejection_reason = None

    user = db.get(User, row.user_id)
    if user:
        user.per_txn_limit = per
        user.daily_limit = daily

    notif = create_notification(
        db,
        user_id=row.user_id,
        type="LIMIT_INCREASE_APPROVED",
        title="Limit increase approved",
        message=(
            f"Your transaction limits were raised to {_money(per)} XAF per transaction "
            f"and {_money(daily)} XAF daily until {row.expires_at.date().isoformat()}."
            + (
                f" Temporary allowance: {_money(spending_cap)} XAF."
                if spending_cap
                else ""
            )
        ),
        priority="HIGH",
        data={
            "request_id": row.id,
            "expires_at": row.expires_at.isoformat(),
            "per_txn_limit": per,
            "daily_limit": daily,
            "spending_cap": spending_cap,
            "duration_days": duration_days,
        },
    )
    audit_service.record(
        db,
        "LIMIT_INCREASE_APPROVED",
        user_id=admin.id,
        entity_type="limit_increase_request",
        entity_id=row.id,
        meta={"subject_user_id": row.user_id, "per_txn": per, "daily": daily,
              "duration_days": duration_days, "spending_cap": spending_cap},
    )
    db.commit()
    db.refresh(row)
    db.refresh(notif)
    _deliver_limit_decision(
        notif,
        event_type="LIMIT_INCREASE_APPROVED",
        payload={
            "request_id": row.id,
            "status": row.status,
            "per_txn_limit": per,
            "daily_limit": daily,
            "spending_cap": spending_cap,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "duration_days": duration_days,
        },
    )
    return row


def reject(
    db: Session, request_id: int, admin: User, reason: str | None = None
) -> LimitIncreaseRequest:
    row = db.get(LimitIncreaseRequest, request_id)
    if not row:
        raise NotFoundError("Limit increase request not found.", code="LIMIT_REQUEST_NOT_FOUND")
    if row.status != LimitIncreaseStatus.PENDING.value:
        raise ConflictError("Only pending requests can be rejected.", code="LIMIT_REQUEST_NOT_PENDING")

    reason_text = (reason or "").strip() or "Your limit increase request was not approved."
    row.status = LimitIncreaseStatus.REJECTED.value
    row.rejection_reason = reason_text
    row.reviewed_by_admin_id = admin.id
    row.reviewed_at = _now()

    notif = create_notification(
        db,
        user_id=row.user_id,
        type="LIMIT_INCREASE_REJECTED",
        title="Limit increase declined",
        message=reason_text,
        priority="HIGH",
        data={"request_id": row.id, "rejection_reason": reason_text},
    )
    audit_service.record(
        db,
        "LIMIT_INCREASE_REJECTED",
        user_id=admin.id,
        entity_type="limit_increase_request",
        entity_id=row.id,
        result="FAILURE",
        meta={"subject_user_id": row.user_id, "reason": reason_text},
    )
    db.commit()
    db.refresh(row)
    db.refresh(notif)
    _deliver_limit_decision(
        notif,
        event_type="LIMIT_INCREASE_REJECTED",
        payload={
            "request_id": row.id,
            "status": row.status,
            "rejection_reason": reason_text,
        },
    )
    return row


def record_debit_against_grant(db: Session, user_id: int, amount: int) -> None:
    """Count a successful debit toward an active grant's spending cap."""
    grant = active_grant(db, user_id)
    if not grant or amount <= 0:
        return
    grant.amount_spent = int(grant.amount_spent or 0) + amount
    if grant.spending_cap is not None and grant.amount_spent >= grant.spending_cap:
        grant.status = LimitIncreaseStatus.EXHAUSTED.value
        user = db.get(User, user_id)
        if user:
            apply_defaults_to_user(db, user)
        notif = create_notification(
            db,
            user_id=user_id,
            type="LIMIT_INCREASE_EXHAUSTED",
            title="Raised limit fully used",
            message=(
                "Your temporary raised transaction limit has been fully used. "
                f"Standard limits of {_money(catalog_service.default_limits(db)[0])} XAF "
                "per transaction now apply. You can request another increase if needed."
            ),
            priority="HIGH",
            data={"request_id": grant.id},
        )
        db.flush()
        # Delivery happens after the surrounding txn commits (caller commits).
        # Emit immediately for live clients; email/FCM also run here after flush.
        _deliver_limit_decision(
            notif,
            event_type="LIMIT_INCREASE_EXHAUSTED",
            payload={"request_id": grant.id, "status": grant.status},
        )
    else:
        db.flush()


def assert_within_limits(db: Session, user: User, amount: int) -> None:
    """Refuse transactions that exceed effective limits, with clear reasons."""
    per, daily = effective_limits(db, user)
    grant = active_grant(db, user.id)
    default_per, _default_daily = catalog_service.default_limits(db)

    if amount > per:
        raise ValidationError(
            f"This transaction exceeds your per-transaction limit of {_money(per)} XAF. "
            "Reduce the amount or request a limit increase.",
            code="PER_TXN_LIMIT_EXCEEDED",
        )

    from app.services import security_service

    spent = security_service.spent_today(db, user.id)
    if spent + amount > daily:
        remaining = max(0, daily - spent)
        raise ValidationError(
            f"This transaction would exceed your daily limit of {_money(daily)} XAF "
            f"({_money(remaining)} XAF remaining today). "
            "Try a smaller amount, wait until tomorrow, or request a limit increase.",
            code="DAILY_LIMIT_EXCEEDED",
        )

    if grant and grant.spending_cap is not None:
        remaining_cap = max(0, int(grant.spending_cap) - int(grant.amount_spent or 0))
        if amount > remaining_cap:
            raise ValidationError(
                f"This transaction exceeds your remaining temporary raised-limit allowance "
                f"of {_money(remaining_cap)} XAF. "
                f"Standard limit is {_money(default_per)} XAF per transaction after the "
                "allowance is used. Request a new limit increase if you need more capacity.",
                code="LIMIT_GRANT_EXHAUSTED",
            )
