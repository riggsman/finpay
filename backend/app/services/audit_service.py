import json

from sqlalchemy.orm import Session

from app.core.context import get_request_context
from app.models.audit import AuditLog


def record(db: Session, action: str, *, user_id: int | None = None,
           entity_type: str | None = None, entity_id=None,
           result: str = "SUCCESS", meta: dict | None = None) -> AuditLog:
    """Append an immutable audit record (SRS section 62). Flushes but does not
    commit; the calling unit of work owns the transaction."""
    ctx = get_request_context()
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        result=result,
        ip=ctx.get("ip"),
        user_agent=(ctx.get("user_agent") or "")[:255] or None,
        request_id=ctx.get("request_id"),
        meta=json.dumps(meta) if meta else None,
    )
    db.add(log)
    db.flush()
    return log


def list_for_user(db: Session, user_id: int, limit: int = 50) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
