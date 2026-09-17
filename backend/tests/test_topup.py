from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def _fund(client, token, amount):
    from .conftest import fund_wallet
    fund_wallet(client, token, amount)


def _topup(client, token, category="airtime", provider="mtn", target="+237650001234",
           amount=1000, pin="1234", key=None):
    headers = auth_headers(token)
    if key:
        headers = {**headers, "Idempotency-Key": key}
    return client.post(
        f"{API}/bill-payments/topup/confirm",
        headers=headers,
        json={"category": category, "provider_id": provider, "target": target,
              "amount": amount, "pin": pin},
    )


def _balance(client, token):
    return client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]


def test_services_catalog_enables_airtime_and_data(client):
    user = register_active_user(client)
    services = client.get(f"{API}/services", headers=auth_headers(user["access_token"])).json()
    enabled = {s["id"] for s in services["services"] if s["enabled"]}
    assert {"electricity", "airtime", "data"} <= enabled


def test_airtime_topup_success_debits(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    r = _topup(client, token, amount=1000)
    assert r.status_code == 200
    assert r.json()["type"] == "AIRTIME"
    assert r.json()["status"] == "SUCCESS"
    assert _balance(client, token) == 499000


def test_data_topup_success(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    r = _topup(client, token, category="data", provider="orange", amount=2000)
    assert r.status_code == 200
    assert r.json()["type"] == "DATA"
    assert _balance(client, token) == 498000


def test_topup_is_idempotent(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    first = _topup(client, token, amount=1000, key="dup-air")
    second = _topup(client, token, amount=1000, key="dup-air")
    assert first.json()["id"] == second.json()["id"]
    assert _balance(client, token) == 499000


def test_topup_wrong_pin(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    r = _topup(client, token, pin="0000")
    assert r.status_code == 401


def test_topup_insufficient_balance(client):
    user = register_active_user(client)
    r = _topup(client, user["access_token"], amount=1000)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_BALANCE"


def test_topup_provider_decline_no_debit(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    r = _topup(client, token, target="+237650000000", amount=5000)  # ...0000 declines
    assert r.status_code == 200
    assert r.json()["status"] == "FAILED"
    assert _balance(client, token) == 500000


def test_topup_unknown_category(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    r = _topup(client, token, category="gaming")
    assert r.status_code == 422
    # Categories are catalog-driven; unknown category+provider resolves as unknown provider.
    assert r.json()["error"]["code"] == "UNKNOWN_PROVIDER"
