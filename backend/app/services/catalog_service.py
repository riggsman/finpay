from sqlalchemy.orm import Session

from app.core.config import settings as app_config
from app.models.catalog import AppSetting, ServiceProvider

# Default provider catalog (SRS 7.5). Editable in the Back Office.
DEFAULT_PROVIDERS = [
    ("electricity", "eneo", "ENEO"),
    ("airtime", "mtn", "MTN"),
    ("airtime", "orange", "Orange"),
    ("data", "mtn", "MTN Data"),
    ("data", "orange", "Orange Data"),
]

# Platform settings editable in the Back Office.
DEFAULT_SETTINGS = [
    ("default_per_txn_limit", str(app_config.DEFAULT_PER_TXN_LIMIT), "int",
     "Default per-transaction limit (minor units)"),
    ("default_daily_limit", str(app_config.DEFAULT_DAILY_LIMIT), "int",
     "Default daily limit (minor units)"),
    ("email_notifications_enabled", "true", "bool", "Send email notifications"),
    ("email_priorities", "HIGH,CRITICAL", "str", "Priorities that trigger email"),
    ("email_from_name", "FinPay", "str", "Email sender display name"),
]


# --- Providers -------------------------------------------------------------

def seed_providers(db: Session) -> None:
    existing = {(p.category, p.provider_id) for p in db.query(ServiceProvider).all()}
    for category, pid, name in DEFAULT_PROVIDERS:
        if (category, pid) not in existing:
            db.add(ServiceProvider(category=category, provider_id=pid, name=name))
    db.commit()


def list_providers(db: Session, category: str, enabled_only: bool = False) -> list[ServiceProvider]:
    q = db.query(ServiceProvider).filter(ServiceProvider.category == category)
    if enabled_only:
        q = q.filter(ServiceProvider.enabled.is_(True))
    return q.order_by(ServiceProvider.name).all()


def get_provider(db: Session, category: str, provider_id: str) -> ServiceProvider | None:
    return (
        db.query(ServiceProvider)
        .filter(ServiceProvider.category == category, ServiceProvider.provider_id == provider_id)
        .one_or_none()
    )


def list_all_providers(db: Session) -> list[ServiceProvider]:
    return db.query(ServiceProvider).order_by(
        ServiceProvider.category, ServiceProvider.name
    ).all()


# --- Settings --------------------------------------------------------------

def seed_settings(db: Session) -> None:
    existing = {s.key for s in db.query(AppSetting).all()}
    for key, value, vtype, label in DEFAULT_SETTINGS:
        if key not in existing:
            db.add(AppSetting(key=key, value=value, value_type=vtype, label=label))
    db.commit()


def _get(db: Session, key: str) -> AppSetting | None:
    return db.query(AppSetting).filter(AppSetting.key == key).one_or_none()


def get_str(db: Session, key: str, default: str = "") -> str:
    s = _get(db, key)
    return s.value if s else default


def get_int(db: Session, key: str, default: int = 0) -> int:
    s = _get(db, key)
    try:
        return int(s.value) if s else default
    except (TypeError, ValueError):
        return default


def get_bool(db: Session, key: str, default: bool = False) -> bool:
    s = _get(db, key)
    if not s:
        return default
    return str(s.value).strip().lower() in ("1", "true", "yes", "on")


def list_settings(db: Session) -> list[dict]:
    return [
        {"key": s.key, "value": s.value, "value_type": s.value_type, "label": s.label}
        for s in db.query(AppSetting).order_by(AppSetting.key).all()
    ]


def update_settings(db: Session, values: dict) -> None:
    for key, value in values.items():
        s = _get(db, key)
        if s is not None:
            s.value = str(value)
    db.commit()
