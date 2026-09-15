from app.core.config import settings

from .conftest import auth_headers, register_active_user, wait_for_status

API = settings.API_V1_PREFIX


def _set_fee(client, admin_token, operation, body):
    return client.put(f"{API}/admin/fees/{operation}", headers=auth_headers(admin_token),
                      json=body)


def _fund(client, token, amount):
    client.post(f"{API}/wallet/add-money", headers=auth_headers(token), json={"amount": amount})


def _balance(client, token):
    return client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]


def test_login_returns_fee_config(client):
    user = register_active_user(client, password="Password123")
    login = client.post(
        f"{API}/auth/login", json={"identifier": user["phone"], "password": "Password123"}
    ).json()
    assert "config" in login
    assert "fees" in login["config"] and "services" in login["config"]


def test_percentage_withdraw_fee_applied(client, admin_token):
    r = _set_fee(client, admin_token, "WITHDRAW",
                 {"fee_type": "PERCENTAGE", "config": {"percent": 2.5}, "active": True})
    assert r.status_code == 200

    user = register_active_user(client)
    _fund(client, user["access_token"], 500000)
    w = client.post(f"{API}/wallet/withdraw", headers=auth_headers(user["access_token"]),
                    json={"amount": 100000, "destination": "Bank", "pin": "1234"})
    assert w.status_code == 200
    assert w.json()["fee"] == 2500
    # amount + fee debited
    assert _balance(client, user["access_token"]) == 500000 - 102500


def test_tiered_fee_quote_and_apply(client, admin_token):
    _set_fee(client, admin_token, "ELECTRICITY", {
        "fee_type": "TIERED",
        "config": {"tiers": [
            {"min": 0, "max": 100000, "fee": 15000},
            {"min": 100001, "max": 150000, "fee": 25000},
            {"min": 150001, "max": None, "fee": 40000},
        ]},
        "active": True,
    })
    user = register_active_user(client)
    token = user["access_token"]

    q = client.get(f"{API}/fees/quote?operation=ELECTRICITY&amount=120000",
                   headers=auth_headers(token)).json()
    assert q["fee"] == 25000  # second tier

    _fund(client, token, 500000)
    vt = client.post(f"{API}/bill-payments/electricity/validate",
                     headers=auth_headers(token),
                     json={"provider_id": "eneo", "meter_number": "1234567890"}).json()["validation_token"]
    txn = client.post(f"{API}/bill-payments/electricity/confirm", headers=auth_headers(token),
                      json={"validation_token": vt, "amount": 100000, "pin": "1234"}).json()
    assert txn["fee"] == 15000  # first tier for 100000
    wait_for_status(client, token, txn["id"])
    # amount + fee debited on settlement
    assert _balance(client, token) == 500000 - 115000


def test_deposit_fee_deducted_from_credit(client, admin_token):
    _set_fee(client, admin_token, "DEPOSIT",
             {"fee_type": "FLAT", "config": {"fee": 500}, "active": True})
    user = register_active_user(client)
    token = user["access_token"]
    client.post(f"{API}/wallet/add-money", headers=auth_headers(token), json={"amount": 100000})
    # credited amount - fee
    assert _balance(client, token) == 100000 - 500


def test_admin_can_disable_service_and_block_operation(client, admin_token):
    # Disable withdraw.
    d = client.put(f"{API}/admin/services/withdraw", headers=auth_headers(admin_token),
                   json={"enabled": False})
    assert d.status_code == 200 and d.json()["enabled"] is False

    user = register_active_user(client)
    _fund(client, user["access_token"], 100000)
    blocked = client.post(f"{API}/wallet/withdraw", headers=auth_headers(user["access_token"]),
                          json={"amount": 1000, "destination": "Bank", "pin": "1234"})
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "SERVICE_DISABLED"


def test_disabled_service_hidden_from_front_store(client, admin_token):
    client.put(f"{API}/admin/services/electricity", headers=auth_headers(admin_token),
               json={"enabled": False})
    user = register_active_user(client)
    services = client.get(f"{API}/services", headers=auth_headers(user["access_token"])).json()
    elec = next(s for s in services["services"] if s["id"] == "electricity")
    assert elec["enabled"] is False


def test_admin_endpoints_require_admin(client):
    user = register_active_user(client)
    r = client.get(f"{API}/admin/fees", headers=auth_headers(user["access_token"]))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_admin_overview(client, admin_token):
    r = client.get(f"{API}/admin/overview", headers=auth_headers(admin_token))
    assert r.status_code == 200
    body = r.json()
    for key in ("users", "transactions", "processed_volume", "fees_collected"):
        assert key in body


def test_invalid_fee_config_rejected(client, admin_token):
    r = _set_fee(client, admin_token, "WITHDRAW",
                 {"fee_type": "TIERED", "config": {"tiers": []}, "active": True})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_FEE_CONFIG"
