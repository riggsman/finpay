from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def _activity_actions(client, token):
    rows = client.get(f"{API}/me/security/activity", headers=auth_headers(token)).json()
    return [r["action"] for r in rows]


def test_login_is_audited(client):
    user = register_active_user(client, password="Password123")
    client.post(f"{API}/auth/login", json={"identifier": user["phone"], "password": "Password123"})
    assert "LOGIN" in _activity_actions(client, user["access_token"])


def test_money_and_security_actions_audited(client):
    user = register_active_user(client)
    token = user["access_token"]
    client.post(f"{API}/wallet/add-money", headers=auth_headers(token), json={"amount": 10000})
    client.put(f"{API}/me/security/pin", headers=auth_headers(token),
               json={"current_pin": "1234", "new_pin": "4321"})
    client.patch(f"{API}/me/security/limits", headers=auth_headers(token),
                 json={"per_txn_limit": 30000000})
    client.post(f"{API}/me/devices", headers=auth_headers(token),
                json={"device_id": "d1", "push_token": "T1"})

    actions = set(_activity_actions(client, token))
    assert {"TRANSACTION_CREATED", "PIN_CHANGED", "LIMITS_UPDATED", "DEVICE_REGISTERED"} <= actions


def test_audit_records_ip(client):
    user = register_active_user(client)
    client.post(f"{API}/wallet/add-money", headers=auth_headers(user["access_token"]),
                json={"amount": 5000})
    rows = client.get(f"{API}/me/security/activity",
                      headers=auth_headers(user["access_token"])).json()
    txn_rows = [r for r in rows if r["action"] == "TRANSACTION_CREATED"]
    assert txn_rows and txn_rows[0]["ip"]  # testclient supplies a client host


def test_refresh_and_logout(client):
    user = register_active_user(client, password="Password123")
    login = client.post(
        f"{API}/auth/login", json={"identifier": user["phone"], "password": "Password123"}
    ).json()
    refresh_token = login["refresh_token"]

    ok = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    access = login["access_token"]
    out = client.post(f"{API}/auth/logout", headers=auth_headers(access))
    assert out.status_code == 200

    # Refresh token is revoked after logout.
    denied = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "REFRESH_TOKEN_REVOKED"


def test_refresh_rejects_access_token(client):
    user = register_active_user(client)
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": user["access_token"]})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN_TYPE"
