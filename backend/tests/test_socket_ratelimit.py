from app.core.config import settings
from app.websocket import socket as socket_module


def test_socket_event_rate_limit(monkeypatch):
    monkeypatch.setattr(settings, "SOCKET_EVENT_LIMIT", 3)
    monkeypatch.setattr(settings, "SOCKET_EVENT_WINDOW", 100.0)
    socket_module._event_times.pop("sid-test", None)

    allowed = [socket_module._rate_ok("sid-test") for _ in range(5)]
    assert allowed == [True, True, True, False, False]

    # A different connection has an independent bucket.
    assert socket_module._rate_ok("sid-other") is True
