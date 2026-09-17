import datetime as dt
import json
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.campay import get_campay_client, normalize_msisdn
from app.models.phone_lookup import PhoneNameLookup

_NAME_KEYS = ("name", "names", "account_name", "customer_name", "full_name", "holder_name")
_OPERATOR_KEYS = ("operator", "carrier", "network")

_ProviderFetcher = Callable[[str], dict]


def _parse_name(data: dict) -> str | None:
    for key in _NAME_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _parse_operator(data: dict) -> str | None:
    for key in _OPERATOR_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _default_fetcher(msisdn: str) -> dict:
    return get_campay_client().holder_info(msisdn)


def _build(row: PhoneNameLookup, source: str) -> dict:
    return {
        "phone": row.phone,
        "name": row.name,
        "operator": row.operator,
        "provider": row.provider,
        "source": source,
        "lookup_count": row.lookup_count,
        "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
    }


def resolve_phone_name(
    db: Session,
    phone: str,
    *,
    provider: str = "campay",
    fetcher: _ProviderFetcher | None = None,
) -> dict:
    """Resolve an account name for a phone number and cache it.

    If the number is already saved the cached value is returned (only the
    lookup count is bumped). Otherwise the provider is queried and the result
    is persisted for future lookups.
    """
    msisdn = normalize_msisdn(phone)

    row = (
        db.query(PhoneNameLookup)
        .filter(PhoneNameLookup.phone == msisdn, PhoneNameLookup.provider == provider)
        .one_or_none()
    )
    if row:
        row.lookup_count += 1
        row.last_checked_at = dt.datetime.now(dt.timezone.utc)
        db.flush()
        return _build(row, "cache")

    data = (fetcher or _default_fetcher)(msisdn)
    data = data or {}

    row = PhoneNameLookup(
        phone=msisdn,
        provider=provider,
        name=_parse_name(data),
        operator=_parse_operator(data),
        raw_response=json.dumps(data, default=str),
    )
    try:
        db.add(row)
        db.flush()
    except IntegrityError:
        # Lost a race with a concurrent worker: re-read and bump the cache.
        db.rollback()
        row = (
            db.query(PhoneNameLookup)
            .filter(PhoneNameLookup.phone == msisdn, PhoneNameLookup.provider == provider)
            .one()
        )
        row.lookup_count += 1
        row.last_checked_at = dt.datetime.now(dt.timezone.utc)
        db.flush()
        return _build(row, "cache")

    return _build(row, provider)