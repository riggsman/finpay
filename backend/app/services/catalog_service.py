import json
import re

from sqlalchemy.orm import Session

from app.core.config import settings as app_config
from app.core.exceptions import ValidationError
from app.models.catalog import AppSetting, ServiceProvider
from app.models.fees import FeeRule, ServiceFlag

# Default provider catalog (SRS 7.5). Editable in the Back Office.
DEFAULT_PROVIDERS = [
    {
        "category": "electricity",
        "provider_id": "eneo",
        "name": "ENEO",
        "flow": "validate_pay",
        "target_label": "Meter number",
        "icon": "⚡",
        "sort_order": 10,
    },
    {
        "category": "airtime",
        "provider_id": "mtn",
        "name": "MTN",
        "flow": "direct_topup",
        "target_label": "Phone number",
        "icon": "📱",
        "sort_order": 10,
    },
    {
        "category": "airtime",
        "provider_id": "orange",
        "name": "Orange",
        "flow": "direct_topup",
        "target_label": "Phone number",
        "icon": "📱",
        "sort_order": 20,
    },
    {
        "category": "data",
        "provider_id": "mtn",
        "name": "MTN Data",
        "flow": "direct_topup",
        "target_label": "Phone number",
        "icon": "🌐",
        "sort_order": 10,
    },
    {
        "category": "data",
        "provider_id": "orange",
        "name": "Orange Data",
        "flow": "direct_topup",
        "target_label": "Phone number",
        "icon": "🌐",
        "sort_order": 20,
    },
]

ALLOWED_FIELD_KEYS = ("phone", "amount", "message")


def default_fields_for(*, category: str, flow: str, target_label: str | None = None) -> list[dict]:
    """Canonical up-to-3 field schema for a provider."""
    phone_label = (target_label or DEFAULT_TARGET_BY_CATEGORY.get(
        category, "Account / phone number"
    )).strip() or "Phone number"
    return [
        {"key": "phone", "enabled": True, "required": True, "label": phone_label},
        {"key": "amount", "enabled": True, "required": True, "label": "Amount"},
        {
            "key": "message",
            "enabled": False,
            "required": False,
            "label": "Message",
        },
    ]


def normalize_fields(
    fields: list | None,
    *,
    category: str,
    flow: str,
    target_label: str | None = None,
) -> list[dict]:
    """Validate and normalize the provider form-field schema (max 3 keys)."""
    if fields is None:
        return default_fields_for(category=category, flow=flow, target_label=target_label)
    if not isinstance(fields, list):
        raise ValidationError("fields must be a list.", code="INVALID_FIELDS")
    if len(fields) > 3:
        raise ValidationError("At most 3 form fields are allowed.", code="TOO_MANY_FIELDS")

    seen: set[str] = set()
    by_key: dict[str, dict] = {}
    for raw in fields:
        if not isinstance(raw, dict):
            raise ValidationError("Each field must be an object.", code="INVALID_FIELD")
        key = str(raw.get("key") or "").strip().lower()
        if key not in ALLOWED_FIELD_KEYS:
            raise ValidationError(
                f"Unknown field key '{key}'. Allowed: phone, amount, message.",
                code="INVALID_FIELD_KEY",
            )
        if key in seen:
            raise ValidationError(f"Duplicate field key '{key}'.", code="DUPLICATE_FIELD_KEY")
        seen.add(key)
        label = str(raw.get("label") or "").strip() or key.replace("_", " ").title()
        by_key[key] = {
            "key": key,
            "enabled": bool(raw.get("enabled", True)),
            "required": bool(raw.get("required", key != "message")),
            "label": label[:80],
        }

    # Always return all three keys so the admin UI can toggle them; disabled ones are omitted in checkout.
    defaults = {
        f["key"]: f
        for f in default_fields_for(category=category, flow=flow, target_label=target_label)
    }
    out = []
    for key in ALLOWED_FIELD_KEYS:
        out.append(by_key.get(key) or defaults[key])
    # Phone label drives legacy target_label when present.
    return out


def fields_from_config(
    config: dict | None,
    *,
    category: str,
    flow: str,
    target_label: str | None = None,
) -> list[dict]:
    cfg = config if isinstance(config, dict) else {}
    return normalize_fields(
        cfg.get("fields"),
        category=category,
        flow=flow,
        target_label=target_label,
    )


def merge_fields_into_config(
    config: dict | None,
    fields: list[dict],
) -> dict:
    cfg = dict(config or {})
    cfg["fields"] = fields
    return cfg


def phone_label_from_fields(fields: list[dict], fallback: str = "Account / phone number") -> str:
    for f in fields:
        if f.get("key") == "phone" and f.get("label"):
            return str(f["label"])
    return fallback


def provider_public_fields(provider: ServiceProvider) -> list[dict]:
    cfg = parse_config(provider.config_json)
    return fields_from_config(
        cfg,
        category=provider.category,
        flow=provider.flow or "direct_topup",
        target_label=provider.target_label,
    )

CATEGORY_LABELS = {
    "electricity": "Electricity",
    "airtime": "Airtime",
    "data": "Data Bundles",
    "water": "Water",
}

DEFAULT_FLOW_BY_CATEGORY = {
    "electricity": "validate_pay",
    "airtime": "direct_topup",
    "data": "direct_topup",
    "water": "direct_topup",
}

DEFAULT_TARGET_BY_CATEGORY = {
    "electricity": "Meter number",
    "airtime": "Phone number",
    "data": "Phone number",
    "water": "Account / meter number",
}

# Platform settings editable in the Back Office.
DEFAULT_SETTINGS = [
    ("default_per_txn_limit", str(app_config.DEFAULT_PER_TXN_LIMIT), "int",
     "Default per-transaction limit (XAF)"),
    ("default_daily_limit", str(app_config.DEFAULT_DAILY_LIMIT), "int",
     "Default daily limit (XAF)"),
    ("email_notifications_enabled", "true", "bool", "Send email notifications"),
    ("email_priorities", "HIGH,CRITICAL", "str", "Priorities that trigger email"),
    ("email_from_name", "FinPay", "str", "Email sender display name"),
]

LIMIT_SETTING_KEYS = {
    "default_per_txn_limit",
    "default_daily_limit",
}

CATEGORY_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


def normalize_category(category: str) -> str:
    return (category or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_provider_id(provider_id: str) -> str:
    return (provider_id or "").strip().lower().replace("-", "_").replace(" ", "_")


def validate_category(category: str) -> str:
    cat = normalize_category(category)
    if not CATEGORY_SLUG_RE.match(cat):
        raise ValidationError(
            "Category must be a lowercase slug (e.g. electricity, cable_tv).",
            code="INVALID_CATEGORY",
        )
    return cat


def validate_provider_id(provider_id: str) -> str:
    pid = normalize_provider_id(provider_id)
    if not PROVIDER_ID_RE.match(pid):
        raise ValidationError(
            "Provider ID must be a lowercase slug (e.g. eneo, camtel).",
            code="INVALID_PROVIDER_ID",
        )
    return pid


def parse_config(raw: str | dict | None) -> dict:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def dump_config(config: dict | None) -> str:
    return json.dumps(config or {}, separators=(",", ":"))


def category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


def ensure_category_service(db: Session, category: str, *, enable: bool = True) -> None:
    """Ensure a front-store service flag exists for the category."""
    flag = db.query(ServiceFlag).filter(ServiceFlag.key == category).one_or_none()
    if flag is None:
        flag = ServiceFlag(
            key=category,
            label=category_label(category),
            kind="service",
            enabled=enable,
            email_enabled=True,
        )
        db.add(flag)
        db.flush()
    # Ensure a fee rule exists so quotes work for new categories.
    op = category.upper()
    rule = db.query(FeeRule).filter(FeeRule.operation == op).one_or_none()
    if rule is None:
        db.add(
            FeeRule(
                operation=op,
                fee_type="FLAT",
                config=json.dumps({"fee": 0}),
                active=True,
            )
        )
        db.flush()


def seed_providers(db: Session) -> None:
    existing = {
        (p.category, p.provider_id): p for p in db.query(ServiceProvider).all()
    }
    for row in DEFAULT_PROVIDERS:
        key = (row["category"], row["provider_id"])
        fields = default_fields_for(
            category=row["category"],
            flow=row.get("flow", "direct_topup"),
            target_label=row.get("target_label"),
        )
        config = merge_fields_into_config({}, fields)
        if key not in existing:
            db.add(
                ServiceProvider(
                    category=row["category"],
                    provider_id=row["provider_id"],
                    name=row["name"],
                    flow=row.get("flow", "direct_topup"),
                    target_label=row.get("target_label", "Account / phone number"),
                    icon=row.get("icon"),
                    sort_order=row.get("sort_order", 100),
                    integration_mode="MOCK",
                    config_json=dump_config(config),
                    enabled=True,
                )
            )
            ensure_category_service(db, row["category"], enable=True)
        else:
            # Backfill fields schema for existing seeded providers.
            provider = existing[key]
            cfg = parse_config(provider.config_json)
            if "fields" not in cfg:
                provider.config_json = dump_config(merge_fields_into_config(cfg, fields))
                if not provider.target_label:
                    provider.target_label = phone_label_from_fields(fields)
            ensure_category_service(db, row["category"], enable=True)
    db.commit()


def list_providers(db: Session, category: str, enabled_only: bool = False) -> list[ServiceProvider]:
    q = db.query(ServiceProvider).filter(ServiceProvider.category == category)
    if enabled_only:
        q = q.filter(ServiceProvider.enabled.is_(True))
    return q.order_by(ServiceProvider.sort_order, ServiceProvider.name).all()


def get_provider(db: Session, category: str, provider_id: str) -> ServiceProvider | None:
    return (
        db.query(ServiceProvider)
        .filter(ServiceProvider.category == category, ServiceProvider.provider_id == provider_id)
        .one_or_none()
    )


def list_all_providers(db: Session) -> list[ServiceProvider]:
    return db.query(ServiceProvider).order_by(
        ServiceProvider.category, ServiceProvider.sort_order, ServiceProvider.name
    ).all()


def list_categories(db: Session) -> list[dict]:
    rows = (
        db.query(ServiceProvider.category)
        .distinct()
        .order_by(ServiceProvider.category)
        .all()
    )
    out = []
    for (cat,) in rows:
        count = (
            db.query(ServiceProvider)
            .filter(ServiceProvider.category == cat, ServiceProvider.enabled.is_(True))
            .count()
        )
        out.append({"category": cat, "label": category_label(cat), "enabled_count": count})
    return out


def create_provider(
    db: Session,
    *,
    category: str,
    provider_id: str,
    name: str,
    description: str | None = None,
    enabled: bool = True,
    flow: str | None = None,
    integration_mode: str = "MOCK",
    base_url: str | None = None,
    config: dict | None = None,
    target_label: str | None = None,
    icon: str | None = None,
    sort_order: int = 100,
) -> ServiceProvider:
    category = validate_category(category)
    provider_id = validate_provider_id(provider_id)
    name = (name or "").strip()
    if not name:
        raise ValidationError("Display name is required.", code="INVALID_NAME")

    flow = (flow or DEFAULT_FLOW_BY_CATEGORY.get(category, "direct_topup")).strip()
    if flow not in ("validate_pay", "direct_topup"):
        raise ValidationError("flow must be validate_pay or direct_topup.", code="INVALID_FLOW")

    integration_mode = (integration_mode or "MOCK").upper()
    if integration_mode not in ("MOCK", "HTTP"):
        raise ValidationError("integration_mode must be MOCK or HTTP.", code="INVALID_MODE")

    if integration_mode == "HTTP" and not (base_url or "").strip():
        raise ValidationError(
            "base_url is required for HTTP integrations.", code="BASE_URL_REQUIRED"
        )

    target_label = (target_label or DEFAULT_TARGET_BY_CATEGORY.get(
        category, "Account / phone number"
    )).strip()

    fields = fields_from_config(
        config,
        category=category,
        flow=flow,
        target_label=target_label,
    )
    # Prefer phone field label as the legacy target_label.
    target_label = phone_label_from_fields(fields, fallback=target_label)
    config = merge_fields_into_config(config, fields)

    provider = ServiceProvider(
        category=category,
        provider_id=provider_id,
        name=name,
        description=(description or None),
        enabled=enabled,
        flow=flow,
        integration_mode=integration_mode,
        base_url=(base_url or None),
        config_json=dump_config(config),
        target_label=target_label,
        icon=icon or None,
        sort_order=int(sort_order or 100),
    )
    db.add(provider)
    ensure_category_service(db, category, enable=True)
    db.flush()
    return provider


def update_provider(db: Session, provider: ServiceProvider, data: dict) -> ServiceProvider:
    if "name" in data and data["name"] is not None:
        name = str(data["name"]).strip()
        if not name:
            raise ValidationError("Display name is required.", code="INVALID_NAME")
        provider.name = name
    if "description" in data:
        provider.description = data["description"] or None
    if "enabled" in data and data["enabled"] is not None:
        provider.enabled = bool(data["enabled"])
    if "flow" in data and data["flow"] is not None:
        flow = str(data["flow"]).strip()
        if flow not in ("validate_pay", "direct_topup"):
            raise ValidationError("flow must be validate_pay or direct_topup.", code="INVALID_FLOW")
        provider.flow = flow
    if "integration_mode" in data and data["integration_mode"] is not None:
        mode = str(data["integration_mode"]).upper()
        if mode not in ("MOCK", "HTTP"):
            raise ValidationError("integration_mode must be MOCK or HTTP.", code="INVALID_MODE")
        provider.integration_mode = mode
    if "base_url" in data:
        provider.base_url = data["base_url"] or None
    if "target_label" in data and data["target_label"] is not None:
        provider.target_label = str(data["target_label"]).strip() or provider.target_label
    if "icon" in data:
        provider.icon = data["icon"] or None
    if "sort_order" in data and data["sort_order"] is not None:
        provider.sort_order = int(data["sort_order"])

    if "config" in data and data["config"] is not None:
        cfg = dict(data["config"] or {})
        fields = fields_from_config(
            cfg,
            category=provider.category,
            flow=provider.flow or "direct_topup",
            target_label=provider.target_label,
        )
        provider.target_label = phone_label_from_fields(fields, fallback=provider.target_label)
        provider.config_json = dump_config(merge_fields_into_config(cfg, fields))
    else:
        # Keep fields in sync when only target_label/flow changed.
        cfg = parse_config(provider.config_json)
        fields = fields_from_config(
            cfg,
            category=provider.category,
            flow=provider.flow or "direct_topup",
            target_label=provider.target_label,
        )
        # If phone label drifted from target_label, prefer target_label.
        for f in fields:
            if f["key"] == "phone":
                f["label"] = provider.target_label
        provider.config_json = dump_config(merge_fields_into_config(cfg, fields))

    if provider.integration_mode == "HTTP" and not (provider.base_url or "").strip():
        raise ValidationError(
            "base_url is required for HTTP integrations.", code="BASE_URL_REQUIRED"
        )

    ensure_category_service(db, provider.category, enable=True)
    db.flush()
    return provider


# --- Settings --------------------------------------------------------------

def seed_settings(db: Session) -> None:
    existing = {s.key: s for s in db.query(AppSetting).all()}
    for key, value, vtype, label in DEFAULT_SETTINGS:
        row = existing.get(key)
        if row is None:
            db.add(AppSetting(key=key, value=value, value_type=vtype, label=label))
        else:
            row.label = label
            row.value_type = vtype
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


def default_limits(db: Session) -> tuple[int, int]:
    return (
        get_int(db, "default_per_txn_limit", app_config.DEFAULT_PER_TXN_LIMIT),
        get_int(db, "default_daily_limit", app_config.DEFAULT_DAILY_LIMIT),
    )


def kyc_approved_limits(db: Session) -> tuple[int, int]:
    return (
        get_int(db, "kyc_approved_per_txn_limit", app_config.KYC_APPROVED_PER_TXN_LIMIT),
        get_int(db, "kyc_approved_daily_limit", app_config.KYC_APPROVED_DAILY_LIMIT),
    )


def sync_user_limits(db: Session) -> None:
    """Re-apply default limits to users without an active raised-limit grant."""
    from app.models.user import User
    from app.services import limit_service

    default_per, default_daily = default_limits(db)
    for user in db.query(User).all():
        if limit_service.active_grant(db, user.id):
            continue
        user.per_txn_limit = default_per
        user.daily_limit = default_daily
    db.flush()


def update_settings(db: Session, values: dict) -> None:
    touched_limits = False
    for key, value in values.items():
        s = _get(db, key)
        if s is not None:
            s.value = str(value)
            if key in LIMIT_SETTING_KEYS:
                touched_limits = True
    if touched_limits:
        sync_user_limits(db)
    db.commit()
