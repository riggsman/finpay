"""Allocate deliverable @local.dev addresses for new accounts."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User

_LOCAL_RE = re.compile(r"[^a-z0-9._+-]+")


def _domain() -> str:
    return (settings.USER_EMAIL_DOMAIN or "local.dev").strip().lower()


def _slug_from_name(first_name: str, phone: str) -> str:
    base = _LOCAL_RE.sub("", (first_name or "").lower())
    if not base:
        digits = re.sub(r"\D", "", phone or "")[-8:] or "user"
        base = f"user{digits}"
    return base[:40]


def _normalize_local(part: str) -> str:
    local = _LOCAL_RE.sub("", (part or "").lower().strip("."))
    return local[:40] if local else ""


def _email_taken(db: Session, email: str, exclude_user_id: int | None) -> bool:
    q = db.query(User).filter(User.email == email)
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    return q.first() is not None


def allocate_user_email(
    db: Session,
    *,
    first_name: str,
    phone: str,
    preferred: str | None = None,
    exclude_user_id: int | None = None,
) -> str:
    """Return a unique email on USER_EMAIL_DOMAIN (e.g. john@local.dev).

    Preferred values on the shared domain are honored; other domains are ignored
    so every account stays deliverable to the local mail catcher.
    """
    domain = _domain()
    preferred = (preferred or "").strip().lower()
    local = ""
    if preferred:
        if preferred.endswith(f"@{domain}"):
            local = _normalize_local(preferred.split("@", 1)[0])
        elif "@" not in preferred:
            local = _normalize_local(preferred)
    if not local:
        local = _slug_from_name(first_name, phone)

    candidate = f"{local}@{domain}"
    if not _email_taken(db, candidate, exclude_user_id):
        return candidate

    n = 2
    while True:
        candidate = f"{local}{n}@{domain}"
        if not _email_taken(db, candidate, exclude_user_id):
            return candidate
        n += 1
