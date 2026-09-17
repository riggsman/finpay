from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.user import User, UserStatus
from app.models.wallet import Wallet
from app.services import catalog_service, fee_service

logger = get_logger("finpay.bootstrap")


def seed_admin(db: Session) -> None:
    admin = (
        db.query(User)
        .filter(or_(User.email == settings.ADMIN_EMAIL, User.phone == settings.ADMIN_PHONE))
        .one_or_none()
    )
    if admin is None:
        admin = User(
            phone=settings.ADMIN_PHONE,
            email=settings.ADMIN_EMAIL,
            first_name="FinPay",
            last_name="Admin",
            status=UserStatus.ACTIVE,
            email_verified=True,
            phone_verified=True,
            is_admin=True,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            transaction_pin_hash=hash_password(settings.DEFAULT_TRANSACTION_PIN),
        )
        db.add(admin)
        db.flush()
        db.add(Wallet(user_id=admin.id, balance=0, currency="XAF"))
        db.commit()
        logger.info("Seeded Back Office admin %s", settings.ADMIN_EMAIL)
    else:
        changed = False
        if not admin.is_admin:
            admin.is_admin = True
            changed = True
        if admin.email != settings.ADMIN_EMAIL:
            admin.email = settings.ADMIN_EMAIL
            changed = True
        if admin.phone != settings.ADMIN_PHONE:
            admin.phone = settings.ADMIN_PHONE
            changed = True
        if admin.status != UserStatus.ACTIVE:
            admin.status = UserStatus.ACTIVE
            changed = True
        # Keep the seeded admin password aligned with settings in non-production
        # so local Back Office login does not drift after domain/config changes.
        if settings.ENVIRONMENT.lower() in {"development", "dev", "local", "test"}:
            from app.core.security import verify_password

            if not admin.password_hash or not verify_password(
                settings.ADMIN_PASSWORD, admin.password_hash
            ):
                admin.password_hash = hash_password(settings.ADMIN_PASSWORD)
                changed = True
        if changed:
            db.commit()
            logger.info("Updated Back Office admin %s", settings.ADMIN_EMAIL)


def seed_all(db: Session) -> None:
    fee_service.seed_defaults(db)
    catalog_service.seed_providers(db)
    catalog_service.seed_settings(db)
    seed_admin(db)
