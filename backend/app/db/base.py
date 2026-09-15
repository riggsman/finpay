from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import models so that Alembic autogenerate and metadata.create_all see them.
from app.models import (  # noqa: E402,F401
    user,
    otp,
    token,
    wallet,
    transaction,
    notification,
    billing,
    password_reset,
    kyc,
    support,
    social,
    device,
    audit,
    fees,
    catalog,
)
