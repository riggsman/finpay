from app.core.config import settings

from .conftest import unique_phone

API = settings.API_V1_PREFIX


def test_login_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "RL_LOGIN_LIMIT", 3)
    phone = unique_phone()
    codes = []
    for _ in range(5):
        r = client.post(f"{API}/auth/login", json={"identifier": phone, "password": "x"})
        codes.append(r.status_code)
    # First 3 attempts hit auth (401), then the limiter kicks in (429).
    assert codes[:3] == [401, 401, 401]
    assert codes[3] == 429
    assert codes[4] == 429

    body = client.post(f"{API}/auth/login", json={"identifier": phone, "password": "x"}).json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["details"]["retry_after_seconds"] > 0


def test_otp_initiate_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "RL_OTP_INITIATE_LIMIT", 2)
    phone = unique_phone()
    codes = [
        client.post(f"{API}/auth/register/initiate", json={"phone": phone}).status_code
        for _ in range(4)
    ]
    assert codes[:2] == [200, 200]
    assert codes[2] == 429


def test_other_identifier_not_affected(client, monkeypatch):
    monkeypatch.setattr(settings, "RL_LOGIN_LIMIT", 2)
    victim = unique_phone()
    for _ in range(3):
        client.post(f"{API}/auth/login", json={"identifier": victim, "password": "x"})
    # A different identifier still gets through (bucketed independently).
    other = unique_phone()
    r = client.post(f"{API}/auth/login", json={"identifier": other, "password": "x"})
    assert r.status_code == 401


def test_rate_limit_disabled_allows(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False)
    phone = unique_phone()
    codes = [
        client.post(f"{API}/auth/login", json={"identifier": phone, "password": "x"}).status_code
        for _ in range(15)
    ]
    assert all(c == 401 for c in codes)
