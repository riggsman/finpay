from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def _fund(client, token, amount):
    from .conftest import fund_wallet
    fund_wallet(client, token, amount)


def test_send_money_moves_funds_between_wallets(client):
    sender = register_active_user(client)
    recipient = register_active_user(client)
    _fund(client, sender["access_token"], 200000)

    r = client.post(
        f"{API}/wallet/send",
        headers=auth_headers(sender["access_token"]),
        json={"recipient": recipient["phone"], "amount": 50000, "pin": "1234"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["type"] == "SEND_MONEY"
    assert r.json()["status"] == "SUCCESS"

    sbal = client.get(f"{API}/wallet", headers=auth_headers(sender["access_token"])).json()
    rbal = client.get(f"{API}/wallet", headers=auth_headers(recipient["access_token"])).json()
    assert sbal["balance"] == 150000
    assert rbal["balance"] == 50000

    rnotifs = client.get(
        f"{API}/notifications", headers=auth_headers(recipient["access_token"])
    ).json()
    assert any(n["type"] == "TRANSFER_RECEIVED" for n in rnotifs)


def test_send_to_self_rejected(client):
    user = register_active_user(client)
    _fund(client, user["access_token"], 100000)
    r = client.post(
        f"{API}/wallet/send",
        headers=auth_headers(user["access_token"]),
        json={"recipient": user["phone"], "amount": 10000, "pin": "1234"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SELF_TRANSFER"


def test_send_to_unknown_recipient(client):
    user = register_active_user(client)
    _fund(client, user["access_token"], 100000)
    r = client.post(
        f"{API}/wallet/send",
        headers=auth_headers(user["access_token"]),
        json={"recipient": "+237600000000", "amount": 10000, "pin": "1234"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RECIPIENT_NOT_FOUND"


def test_send_wrong_pin_rejected(client):
    sender = register_active_user(client)
    recipient = register_active_user(client)
    _fund(client, sender["access_token"], 100000)
    r = client.post(
        f"{API}/wallet/send",
        headers=auth_headers(sender["access_token"]),
        json={"recipient": recipient["phone"], "amount": 10000, "pin": "0000"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_PIN"


def test_send_insufficient_balance(client):
    sender = register_active_user(client)
    recipient = register_active_user(client)
    r = client.post(
        f"{API}/wallet/send",
        headers=auth_headers(sender["access_token"]),
        json={"recipient": recipient["phone"], "amount": 10000, "pin": "1234"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_BALANCE"


def test_send_is_idempotent(client):
    sender = register_active_user(client)
    recipient = register_active_user(client)
    _fund(client, sender["access_token"], 200000)
    headers = {**auth_headers(sender["access_token"]), "Idempotency-Key": "send-dup"}
    first = client.post(
        f"{API}/wallet/send", headers=headers,
        json={"recipient": recipient["phone"], "amount": 50000, "pin": "1234"},
    )
    second = client.post(
        f"{API}/wallet/send", headers=headers,
        json={"recipient": recipient["phone"], "amount": 50000, "pin": "1234"},
    )
    assert first.json()["id"] == second.json()["id"]
    sbal = client.get(f"{API}/wallet", headers=auth_headers(sender["access_token"])).json()
    assert sbal["balance"] == 150000  # only one debit


def test_withdraw_debits_wallet(client):
    user = register_active_user(client)
    _fund(client, user["access_token"], 100000)
    r = client.post(
        f"{API}/wallet/withdraw",
        headers=auth_headers(user["access_token"]),
        json={"amount": 30000, "destination": "Bank ****1234", "pin": "1234"},
    )
    assert r.status_code == 200
    assert r.json()["type"] == "WITHDRAW"
    assert r.json()["status"] == "SUCCESS"
    bal = client.get(f"{API}/wallet", headers=auth_headers(user["access_token"])).json()
    assert bal["balance"] == 70000


def test_withdraw_insufficient_balance(client):
    user = register_active_user(client)
    _fund(client, user["access_token"], 10000)
    r = client.post(
        f"{API}/wallet/withdraw",
        headers=auth_headers(user["access_token"]),
        json={"amount": 50000, "destination": "Bank ****1234", "pin": "1234"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
