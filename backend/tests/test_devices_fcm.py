from types import SimpleNamespace

from app.core.config import settings
from app.notifications import fcm

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def _notif(user_id=1, priority="NORMAL"):
    return SimpleNamespace(
        user_id=user_id, priority=priority, title="t", message="m",
        event_id="evt_x", id=1, type="TEST",
    )


# --- Device registration ---------------------------------------------------

def test_push_config_reports_disabled_by_default(client):
    user = register_active_user(client)
    r = client.get(f"{API}/me/devices/config", headers=auth_headers(user["access_token"]))
    assert r.status_code == 200
    assert r.json()["fcm_enabled"] is False


def test_register_and_list_device(client):
    user = register_active_user(client)
    h = auth_headers(user["access_token"])
    r = client.post(f"{API}/me/devices", headers=h,
                    json={"device_id": "dev-1", "device_type": "web", "push_token": "TKN-A"})
    assert r.status_code == 200
    body = r.json()
    assert body["push_enabled"] is True
    assert "push_token" not in body
    assert "device_id" not in body

    devices = client.get(f"{API}/me/devices", headers=h).json()
    assert len(devices) == 1
    assert devices[0]["device_type"] == "web"
    assert "device_id" not in devices[0]
    assert "push_token" not in devices[0]


def test_reregister_same_device_updates_token(client):
    user = register_active_user(client)
    h = auth_headers(user["access_token"])
    first = client.post(f"{API}/me/devices", headers=h,
                        json={"device_id": "dev-1", "push_token": "TKN-A"}).json()
    second = client.post(f"{API}/me/devices", headers=h,
                         json={"device_id": "dev-1", "push_token": "TKN-B"}).json()
    assert first["id"] == second["id"]
    assert len(client.get(f"{API}/me/devices", headers=h).json()) == 1


def test_token_move_detaches_from_previous_owner(client):
    a = register_active_user(client)
    b = register_active_user(client)
    client.post(f"{API}/me/devices", headers=auth_headers(a["access_token"]),
                json={"device_id": "browser-x", "push_token": "SHARED-TOKEN"})
    # Same physical browser now registers under user B with the same token.
    client.post(f"{API}/me/devices", headers=auth_headers(b["access_token"]),
                json={"device_id": "browser-x", "push_token": "SHARED-TOKEN"})

    a_devices = client.get(f"{API}/me/devices", headers=auth_headers(a["access_token"])).json()
    # The token no longer belongs to user A.
    assert all(not d["push_enabled"] for d in a_devices)
    b_devices = client.get(f"{API}/me/devices", headers=auth_headers(b["access_token"])).json()
    assert any(d["push_enabled"] for d in b_devices)


def test_unregister_device(client):
    user = register_active_user(client)
    h = auth_headers(user["access_token"])
    did = client.post(f"{API}/me/devices", headers=h,
                      json={"device_id": "dev-1", "push_token": "TKN-A"}).json()["id"]
    assert client.delete(f"{API}/me/devices/{did}", headers=h).status_code == 200
    assert client.get(f"{API}/me/devices", headers=h).json() == []


# --- FCM dispatch policy ---------------------------------------------------

def test_should_send_when_user_offline(monkeypatch):
    monkeypatch.setattr(fcm, "is_user_connected", lambda uid: False)
    assert fcm.should_send(_notif(priority="NORMAL")) is True


def test_should_not_send_when_connected_and_normal(monkeypatch):
    monkeypatch.setattr(fcm, "is_user_connected", lambda uid: True)
    assert fcm.should_send(_notif(priority="NORMAL")) is False


def test_should_send_when_connected_but_critical(monkeypatch):
    monkeypatch.setattr(fcm, "is_user_connected", lambda uid: True)
    assert fcm.should_send(_notif(priority="CRITICAL")) is True


def test_maybe_send_is_noop_when_not_configured(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(fcm, "_send", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    # Not configured (default in tests) => no send even if policy would allow it.
    monkeypatch.setattr(fcm, "is_user_connected", lambda uid: False)
    fcm.maybe_send(_notif())
    assert called["n"] == 0
