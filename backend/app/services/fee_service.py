import json

from sqlalchemy.orm import Session

from app.models.fees import FeeRule, ServiceFlag

# Fee-bearing operations (SRS section 71.1).
FEE_OPERATIONS = ["DEPOSIT", "WITHDRAW", "SEND_MONEY", "ELECTRICITY", "AIRTIME", "DATA"]

# Front-store services, money operations, funding methods, and notification email categories.
DEFAULT_SERVICE_FLAGS = [
    ("electricity", "Electricity", "service", True, True),
    ("airtime", "Airtime", "service", True, True),
    ("data", "Data Bundles", "service", True, True),
    ("water", "Water", "service", False, True),
    ("add_money", "Add Money", "operation", True, True),
    ("withdraw", "Withdraw", "operation", True, True),
    ("send_money", "Send Money", "operation", True, True),
    # Deposit funding rails shown on Add Money (admin-togglable).
    ("funding_card", "Deposit — Card", "funding", True, False),
    ("funding_bank", "Deposit — Bank transfer", "funding", True, False),
    ("funding_mobile_money", "Deposit — Mobile money", "funding", True, False),
    ("kyc", "KYC verification", "notification", True, True),
    ("security", "Security alerts", "notification", True, True),
    ("support", "Support & disputes", "notification", True, True),
]


def seed_defaults(db: Session) -> None:
    """Create default (zero) fee rules and service flags if missing. Idempotent."""
    existing_ops = {r.operation for r in db.query(FeeRule).all()}
    for op in FEE_OPERATIONS:
        if op not in existing_ops:
            db.add(FeeRule(operation=op, fee_type="FLAT",
                           config=json.dumps({"fee": 0}), active=True))

    existing_keys = {f.key for f in db.query(ServiceFlag).all()}
    for key, label, kind, enabled, email_enabled in DEFAULT_SERVICE_FLAGS:
        if key not in existing_keys:
            db.add(ServiceFlag(
                key=key, label=label, kind=kind,
                enabled=enabled, email_enabled=email_enabled,
            ))
    db.commit()


def _rule_config(rule: FeeRule) -> dict:
    try:
        return json.loads(rule.config) if rule.config else {}
    except Exception:
        return {}


def compute_fee(db: Session, operation: str, amount: int) -> int:
    """Return the fee (minor units) for an operation and amount using the active
    fee rule. Returns 0 when there is no active rule."""
    rule = db.query(FeeRule).filter(FeeRule.operation == operation).one_or_none()
    if not rule or not rule.active:
        return 0
    return _fee_from_rule(rule.fee_type, _rule_config(rule), amount)


def attach_fee(db: Session, txn, operation: str, amount: int) -> int:
    """Stamp the configured service fee onto a transaction before any ledger move.

    Call this before debiting/crediting the wallet. Outbound flows should then
    debit ``amount + fee``; deposits should credit ``amount - fee``.
    """
    from app.core.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError("Amount must be positive.", code="INVALID_AMOUNT")
    fee = compute_fee(db, operation, amount)
    txn.amount = int(amount)
    txn.fee = int(fee)
    return fee


def _fee_from_rule(fee_type: str, cfg: dict, amount: int) -> int:
    if fee_type == "FLAT":
        return max(0, int(cfg.get("fee", 0)))
    if fee_type == "PERCENTAGE":
        percent = float(cfg.get("percent", 0) or 0)
        fee = int(round(amount * percent / 100.0))
        min_fee = cfg.get("min_fee")
        max_fee = cfg.get("max_fee")
        if min_fee is not None:
            fee = max(fee, int(min_fee))
        if max_fee is not None:
            fee = min(fee, int(max_fee))
        return max(0, fee)
    if fee_type == "TIERED":
        for tier in cfg.get("tiers", []):
            lo = int(tier.get("min", 0))
            hi = tier.get("max")
            hi = int(hi) if hi is not None else None
            if amount >= lo and (hi is None or amount <= hi):
                return max(0, int(tier.get("fee", 0)))
        return 0
    return 0


def quote(db: Session, operation: str, amount: int) -> dict:
    fee = compute_fee(db, operation, amount)
    return {"operation": operation, "amount": amount, "fee": fee, "total": amount + fee}


def get_fee_config(db: Session) -> dict:
    """Fee configuration for client caching (SRS section 71.4)."""
    out = {}
    for rule in db.query(FeeRule).all():
        out[rule.operation] = {
            "fee_type": rule.fee_type,
            "active": rule.active,
            "config": _rule_config(rule),
        }
    return out


def get_service_flags(db: Session, enabled_only: bool = False) -> list[dict]:
    q = db.query(ServiceFlag)
    if enabled_only:
        q = q.filter(ServiceFlag.enabled.is_(True))
    return [
        {
            "key": f.key,
            "label": f.label,
            "kind": f.kind,
            "enabled": f.enabled,
            "email_enabled": f.email_enabled,
        }
        for f in q.order_by(ServiceFlag.kind, ServiceFlag.key).all()
    ]


def is_service_enabled(db: Session, key: str) -> bool:
    flag = db.query(ServiceFlag).filter(ServiceFlag.key == key).one_or_none()
    return True if flag is None else flag.enabled


def is_email_enabled(db: Session, key: str) -> bool:
    """Whether email alerts are on for a service. Missing flags default to True."""
    flag = db.query(ServiceFlag).filter(ServiceFlag.key == key).one_or_none()
    return True if flag is None else bool(flag.email_enabled)


def ensure_enabled(db: Session, key: str) -> None:
    from app.core.exceptions import AppError

    if not is_service_enabled(db, key):
        raise AppError("This service is currently unavailable.",
                       code="SERVICE_DISABLED", status_code=403)


def get_client_config(db: Session) -> dict:
    return {
        "fees": get_fee_config(db),
        "services": get_service_flags(db),
        "funding_methods": {
            "card": is_service_enabled(db, "funding_card"),
            "bank": is_service_enabled(db, "funding_bank"),
            "mobile_money": is_service_enabled(db, "funding_mobile_money"),
        },
    }
