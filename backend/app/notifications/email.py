"""Email notification channel.

Backends (EMAIL_BACKEND):
  - "console"  : logs the email (default; useful in development and tests)
  - "smtp"     : sends via SMTP using the SMTP_* settings
  - "disabled" : no-op

Whether email is used at all is also gated by the Back Office setting
`email_notifications_enabled` and the `email_priorities` list.
"""
import smtplib
import threading
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import SessionLocal
from app.models.user import User
from app.services import catalog_service

logger = get_logger("finpay.email")

# Captured sends for the console backend (used by tests).
sent_log: list[dict] = []


def _send_console(to: str, subject: str, body: str) -> None:
    sent_log.append({"to": to, "subject": subject, "body": body})
    logger.info("EMAIL (console) to=%s subject=%s", to, subject)


def _send_smtp(to: str, subject: str, body: str, from_name: str) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{settings.EMAIL_FROM}>"
    msg["To"] = to
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)
    logger.info("EMAIL (smtp) sent to=%s subject=%s", to, subject)


def send_email(to: str, subject: str, body: str, from_name: str = "FinPay") -> bool:
    backend = settings.EMAIL_BACKEND.lower()
    if not to or backend == "disabled":
        return False
    try:
        if backend == "smtp":
            if not settings.SMTP_HOST:
                logger.info("SMTP not configured; skipping email to %s", to)
                return False
            _send_smtp(to, subject, body, from_name)
        else:
            _send_console(to, subject, body)
        return True
    except Exception:
        logger.exception("Email send failed to %s", to)
        return False


def resolve_email(notification) -> dict | None:
    """Return the email to send for a notification, or None if not eligible."""
    if settings.EMAIL_BACKEND.lower() == "disabled":
        return None
    db = SessionLocal()
    try:
        if not catalog_service.get_bool(db, "email_notifications_enabled", True):
            return None
        priorities = {
            p.strip().upper()
            for p in catalog_service.get_str(db, "email_priorities", "HIGH,CRITICAL").split(",")
            if p.strip()
        }
        if (notification.priority or "NORMAL").upper() not in priorities:
            return None
        user = db.get(User, notification.user_id)
        if not user or not user.email:
            return None
        from_name = catalog_service.get_str(db, "email_from_name", "FinPay")
        return {
            "to": user.email,
            "subject": f"[{from_name}] {notification.title}",
            "body": f"{notification.message}\n\n— {from_name}",
            "from_name": from_name,
        }
    finally:
        db.close()


def maybe_send(notification) -> None:
    """Deliver a persisted notification by email when enabled and eligible."""
    msg = resolve_email(notification)
    if not msg:
        return
    threading.Thread(
        target=send_email,
        args=(msg["to"], msg["subject"], msg["body"], msg["from_name"]),
        daemon=True,
    ).start()
