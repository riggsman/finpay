import datetime as dt
import uuid


def new_event_id() -> str:
    return "evt_" + uuid.uuid4().hex


def make_envelope(event_type: str, user_id: int, data: dict,
                  event_id: str | None = None) -> dict:
    """Standard real-time event envelope (SRS section 24)."""
    return {
        "event_id": event_id or new_event_id(),
        "event_type": event_type,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "user_id": user_id,
        "data": data,
    }
