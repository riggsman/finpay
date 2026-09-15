from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def _fund(client, token, amount):
    client.post(f"{API}/wallet/add-money", headers=auth_headers(token), json={"amount": amount})


def _withdraw(client, token, amount, pin="1234"):
    return client.post(
        f"{API}/wallet/withdraw",
        headers=auth_headers(token),
        json={"amount": amount, "destination": "Bank ****1", "pin": pin},
    )


def test_update_profile(client):
    user = register_active_user(client)
    r = client.patch(
        f"{API}/me/profile",
        headers=auth_headers(user["access_token"]),
        json={"first_name": "Secure", "last_name": "Person"},
    )
    assert r.status_code == 200
    assert r.json()["first_name"] == "Secure"
    assert r.json()["last_name"] == "Person"


def test_change_password_revokes_sessions(client):
    user = register_active_user(client, password="OldPass123")
    phone = user["phone"]

    r = client.post(
        f"{API}/me/security/change-password",
        headers=auth_headers(user["access_token"]),
        json={"current_password": "OldPass123", "new_password": "NewPass456"},
    )
    assert r.status_code == 200

    assert client.post(
        f"{API}/auth/login", json={"identifier": phone, "password": "OldPass123"}
    ).status_code == 401
    assert client.post(
        f"{API}/auth/login", json={"identifier": phone, "password": "NewPass456"}
    ).status_code == 200


def test_change_password_wrong_current_rejected(client):
    user = register_active_user(client, password="OldPass123")
    r = client.post(
        f"{API}/me/security/change-password",
        headers=auth_headers(user["access_token"]),
        json={"current_password": "wrong", "new_password": "NewPass456"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_PASSWORD"


def test_change_pin_and_old_pin_invalidated(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 100000)

    # Wrong current PIN rejected.
    bad = client.put(
        f"{API}/me/security/pin",
        headers=auth_headers(token),
        json={"current_pin": "0000", "new_pin": "4321"},
    )
    assert bad.status_code == 401

    ok = client.put(
        f"{API}/me/security/pin",
        headers=auth_headers(token),
        json={"current_pin": "1234", "new_pin": "4321"},
    )
    assert ok.status_code == 200

    # Old PIN no longer authorises a payment; the new one does.
    assert _withdraw(client, token, 5000, pin="1234").status_code == 401
    assert _withdraw(client, token, 5000, pin="4321").status_code == 200


def test_per_transaction_limit_enforced(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    client.patch(
        f"{API}/me/security/limits",
        headers=auth_headers(token),
        json={"per_txn_limit": 10000},
    )
    over = _withdraw(client, token, 20000)
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "PER_TXN_LIMIT_EXCEEDED"
    assert _withdraw(client, token, 5000).status_code == 200


def test_daily_limit_enforced(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    resp = client.patch(
        f"{API}/me/security/limits",
        headers=auth_headers(token),
        json={"per_txn_limit": 15000, "daily_limit": 15000},
    )
    assert resp.status_code == 200
    assert _withdraw(client, token, 10000).status_code == 200
    second = _withdraw(client, token, 10000)  # 20000 total > 15000 daily
    assert second.status_code == 422
    assert second.json()["error"]["code"] == "DAILY_LIMIT_EXCEEDED"


def test_invalid_limit_range_rejected(client):
    user = register_active_user(client)
    r = client.patch(
        f"{API}/me/security/limits",
        headers=auth_headers(user["access_token"]),
        json={"per_txn_limit": 100000, "daily_limit": 5000},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_LIMIT_RANGE"


def test_sessions_list_and_revoke(client):
    user = register_active_user(client, password="Password123")
    token = user["access_token"]
    # Create extra sessions via login.
    for _ in range(2):
        client.post(
            f"{API}/auth/login", json={"identifier": user["phone"], "password": "Password123"}
        )
    sessions = client.get(f"{API}/me/security/sessions", headers=auth_headers(token)).json()
    assert len(sessions) >= 3

    revoke = client.post(
        f"{API}/me/security/sessions/revoke-all", headers=auth_headers(token)
    )
    assert revoke.status_code == 200

    after = client.get(f"{API}/me/security/sessions", headers=auth_headers(token)).json()
    assert after == []
