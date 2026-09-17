from app.core.config import settings
from app.notifications import email as email_channel

from .conftest import auth_headers, register_active_user, unique_phone

API = settings.API_V1_PREFIX


def test_register_verify_login_flow(client):
    phone = unique_phone()

    r = client.post(f"{API}/auth/register/initiate", json={"phone": phone})
    assert r.status_code == 200
    assert r.json()["otp_debug"]

    r = client.post(
        f"{API}/auth/register",
        json={
            "phone": phone,
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": f"{phone.strip('+')}@example.com",
            "password": "Password123",
        },
    )
    assert r.status_code == 200

    otp = client.post(f"{API}/auth/register/initiate", json={"phone": phone}).json()["otp_debug"]

    # Wrong OTP is rejected.
    bad = client.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": "000000"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "OTP_INCORRECT"

    # Correct OTP activates and returns tokens.
    good = client.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": otp})
    assert good.status_code == 200
    body = good.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["status"] == "ACTIVE"

    # Login works with the same credentials.
    login = client.post(
        f"{API}/auth/login", json={"identifier": phone, "password": "Password123"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["phone"] == phone


def test_registration_otp_is_emailed(client, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "console")
    email_channel.sent_log.clear()
    phone = unique_phone()
    client.post(
        f"{API}/auth/register",
        json={
            "phone": phone,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "password": "Password123",
        },
    )
    assert email_channel.sent_log, "OTP should be emailed after register"
    first = email_channel.sent_log[-1]
    assert first["to"].endswith("@local.dev")
    assert "verification code" in first["body"].lower()

    otp = client.post(f"{API}/auth/register/initiate", json={"phone": phone}).json()["otp_debug"]
    assert otp in email_channel.sent_log[-1]["body"]


def test_login_with_wrong_password_rejected(client):
    user = register_active_user(client)
    r = client.post(
        f"{API}/auth/login", json={"identifier": user["phone"], "password": "nope"}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_protected_route_requires_auth(client):
    r = client.get(f"{API}/me")
    assert r.status_code == 401

    user = register_active_user(client)
    ok = client.get(f"{API}/me", headers=auth_headers(user["access_token"]))
    assert ok.status_code == 200
    assert ok.json()["phone"] == user["phone"]
