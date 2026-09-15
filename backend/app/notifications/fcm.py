"""Firebase Cloud Messaging integration.

Supply credentials via one of:
  - FCM_SERVICE_ACCOUNT_JSON: the full service-account JSON (recommended secret)
  - FIREBASE_PROJECT_ID + FIREBASE_CLIENT_EMAIL + FIREBASE_PRIVATE_KEY
  - GOOGLE_APPLICATION_CREDENTIALS: path to a service-account file

When no credentials are configured the module is disabled and all sends become
no-ops, so the application runs and delivers notifications via Socket.IO only.
"""
import json
import threading

from app.core.config import settings
from app.core.logging import get_logger
from app.db.database import SessionLocal
from app.models.device import UserDevice
from app.websocket.socket import is_user_connected

logger = get_logger("finpay.fcm")

_app = None
_init_attempted = False
_lock = threading.Lock()


def _build_credentials():
    from firebase_admin import credentials

    if settings.FCM_SERVICE_ACCOUNT_JSON:
        info = json.loads(settings.FCM_SERVICE_ACCOUNT_JSON)
        return credentials.Certificate(info)
    if settings.GOOGLE_APPLICATION_CREDENTIALS:
        return credentials.Certificate(settings.GOOGLE_APPLICATION_CREDENTIALS)
    # Individual fields. Private keys pasted into env often carry literal "\n".
    info = {
        "type": "service_account",
        "project_id": settings.FIREBASE_PROJECT_ID,
        "client_email": settings.FIREBASE_CLIENT_EMAIL,
        "private_key": settings.FIREBASE_PRIVATE_KEY.replace("\\n", "\n"),
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return credentials.Certificate(info)


def _get_app():
    global _app, _init_attempted
    if _app is not None:
        return _app
    with _lock:
        if _app is not None:
            return _app
        if _init_attempted:
            return None
        _init_attempted = True
        if not settings.fcm_configured:
            logger.info("FCM disabled (no credentials configured)")
            return None
        try:
            import firebase_admin

            _app = firebase_admin.initialize_app(_build_credentials(), name="finpay-fcm")
            logger.info("FCM initialized")
        except Exception:
            logger.exception("FCM initialization failed; push disabled")
            _app = None
        return _app


def is_enabled() -> bool:
    return _get_app() is not None


def _active_tokens(db, user_id: int) -> list[str]:
    rows = (
        db.query(UserDevice)
        .filter(
            UserDevice.user_id == user_id,
            UserDevice.is_active.is_(True),
            UserDevice.push_token.isnot(None),
        )
        .all()
    )
    return [r.push_token for r in rows if r.push_token]


def _send(user_id: int, title: str, body: str, data: dict) -> None:
    app = _get_app()
    if app is None:
        return
    from firebase_admin import messaging

    db = SessionLocal()
    try:
        tokens = _active_tokens(db, user_id)
        if not tokens:
            return
        message = messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
        )
        resp = messaging.send_each_for_multicast(message, app=app)
        # Deactivate tokens the provider reports as no longer valid.
        invalid = 0
        for token, result in zip(tokens, resp.responses):
            if not result.success and _is_unregistered(result.exception):
                (
                    db.query(UserDevice)
                    .filter(UserDevice.push_token == token)
                    .update({UserDevice.is_active: False})
                )
                invalid += 1
        if invalid:
            db.commit()
        logger.info("FCM sent to user=%s success=%d/%d", user_id,
                    resp.success_count, len(tokens))
    except Exception:
        logger.exception("FCM send failed for user=%s", user_id)
    finally:
        db.close()


def _is_unregistered(exc) -> bool:
    try:
        from firebase_admin import exceptions, messaging

        return isinstance(
            exc, (messaging.UnregisteredError, exceptions.NotFoundError,
                  exceptions.InvalidArgumentError)
        )
    except Exception:
        return False


def should_send(notification) -> bool:
    """Policy (SRS section 52): push when the user has no active socket session,
    or always for configured high-priority events."""
    priority = (notification.priority or "NORMAL").upper()
    return (not is_user_connected(notification.user_id)) or (
        priority in settings.fcm_always_priorities
    )


def maybe_send(notification) -> None:
    """Deliver a persisted notification via FCM when appropriate."""
    if not settings.fcm_configured or not should_send(notification):
        return
    # Offload so we never block the request / event path on a network call.
    data = {"event_id": notification.event_id, "type": notification.type,
            "notification_id": str(notification.id)}
    threading.Thread(
        target=_send,
        args=(notification.user_id, notification.title, notification.message, data),
        daemon=True,
    ).start()
