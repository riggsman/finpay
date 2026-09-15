from app.core.config import settings

from .conftest import register_active_user

API = settings.API_V1_PREFIX


def _request_code(client, identifier):
    r = client.post(f"{API}/auth/password-reset/request", json={"identifier": identifier})
    assert r.status_code == 200
    return r.json()["reset_code_debug"]


def test_password_reset_happy_path(client):
    user = register_active_user(client, password="OldPass123")
    phone = user["phone"]

    # Old password works.
    assert client.post(
        f"{API}/auth/login", json={"identifier": phone, "password": "OldPass123"}
    ).status_code == 200

    code = _request_code(client, phone)

    verify = client.post(
        f"{API}/auth/password-reset/verify", json={"identifier": phone, "code": code}
    )
    assert verify.status_code == 200
    reset_token = verify.json()["reset_token"]

    complete = client.post(
        f"{API}/auth/password-reset/complete",
        json={"reset_token": reset_token, "new_password": "NewPass456"},
    )
    assert complete.status_code == 200

    # Old password no longer works; new one does.
    assert client.post(
        f"{API}/auth/login", json={"identifier": phone, "password": "OldPass123"}
    ).status_code == 401
    assert client.post(
        f"{API}/auth/login", json={"identifier": phone, "password": "NewPass456"}
    ).status_code == 200


def test_wrong_code_rejected(client):
    user = register_active_user(client)
    _request_code(client, user["phone"])
    r = client.post(
        f"{API}/auth/password-reset/verify",
        json={"identifier": user["phone"], "code": "000000"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "RESET_CODE_INCORRECT"


def test_reset_token_cannot_be_reused(client):
    user = register_active_user(client)
    code = _request_code(client, user["phone"])
    reset_token = client.post(
        f"{API}/auth/password-reset/verify",
        json={"identifier": user["phone"], "code": code},
    ).json()["reset_token"]

    first = client.post(
        f"{API}/auth/password-reset/complete",
        json={"reset_token": reset_token, "new_password": "FirstNew123"},
    )
    assert first.status_code == 200
    second = client.post(
        f"{API}/auth/password-reset/complete",
        json={"reset_token": reset_token, "new_password": "SecondNew123"},
    )
    assert second.status_code == 422
    assert second.json()["error"]["code"] == "RESET_TOKEN_INVALID"


def test_request_for_unknown_identifier_is_generic(client):
    # No account: still returns 200 generic message, no code exposed.
    r = client.post(
        f"{API}/auth/password-reset/request", json={"identifier": "+237600000000"}
    )
    assert r.status_code == 200
    assert r.json()["reset_code_debug"] is None
