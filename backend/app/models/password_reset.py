import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    # Phase 1: a short code delivered to the user.
    code: Mapped[str] = mapped_column(String(12), nullable=False)
    code_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    code_expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Phase 2: an opaque reset token issued once the code is verified.
    reset_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
    token_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
