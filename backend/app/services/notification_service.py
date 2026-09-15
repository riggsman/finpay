import json

from sqlalchemy.orm import Session

from app.events.envelope import new_event_id
from app.models.notification import Notification
from app.websocket.socket import emit_to_user


def create_notification(
    db: Session,
    *,
    user_id: int,
    type: str,
    title: str,
    message: str,
    priority: str = "NORMAL",
    data: dict | None = None,
    event_id: str | None = None,
) -> Notification:
    """Persist a notification (source of truth) then deliver via Socket.IO.

    Per the SRS, every important notification must first be persisted; Socket.IO
    is a delivery mechanism, not storage.
    """
    event_id = event_id or new_event_id()

    # Deduplicate by event_id (SRS section 53).
    existing = (
        db.query(Notification).filter(Notification.event_id == event_id).one_or_none()
    )
    if existing:
        return existing

    notification = Notification(
        event_id=event_id,
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        priority=priority,
        data=json.dumps(data) if data else None,
    )
    db.add(notification)
    db.flush()
    return notification


def deliver_notification(notification: Notification) -> None:
    """Deliver a persisted notification over Socket.IO and, per policy, FCM.

    The database notification is the source of truth; Socket.IO and FCM are
    delivery channels (SRS sections 20 and 52).
    """
    emit_to_user(
        notification.user_id,
        "notification:new",
        {
            "notification_id": notification.id,
            "type": notification.type,
            "title": notification.title,
            "message": notification.message,
            "priority": notification.priority,
        },
        event_id=notification.event_id,
    )
    # Complementary background channels (each no-ops when not configured/eligible).
    from app.notifications import email, fcm

    fcm.maybe_send(notification)
    email.maybe_send(notification)
