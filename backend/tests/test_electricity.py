from app.core.config import settings

from .conftest import auth_headers, register_active_user, wait_for_status

API = settings.API_V1_PREFIX


def _fund(client, token, amount):
    client.post(f"{API}/wallet/add-money", headers=auth_headers(token), json={"amount": amount})


def _validate(client, token, meter="1234567890"):
    r = client.post(
        f"{API}/bill-payments/electricity/validate",
        headers=auth_headers(token),
        json={"provider_id": "eneo", "meter_number": meter},
    )
    assert r.status_code == 200, r.text
    return r.json()["validation_token"]


def test_meter_validation_returns_customer(client):
    user = register_active_user(client)
    r = client.post(
        f"{API}/bill-payments/electricity/validate",
        headers=auth_headers(user["access_token"]),
        json={"provider_id": "eneo", "meter_number": "1234567890"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["validation_token"].startswith("val_")
    assert body["customer"]["name"]
    assert body["provider"]["id"] == "eneo"


def test_invalid_meter_rejected(client):
    user = register_active_user(client)
    r = client.post(
        f"{API}/bill-payments/electricity/validate",
        headers=auth_headers(user["access_token"]),
        json={"provider_id": "eneo", "meter_number": "12"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_METER"


def test_electricity_payment_success_debits_wallet(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 300000)
    vtoken = _validate(client, token)

    r = client.post(
        f"{API}/bill-payments/electricity/confirm",
        headers=auth_headers(token),
        json={"validation_token": vtoken, "amount": 100000, "pin": "1234"},
    )
    assert r.status_code == 200, r.text
    txn = r.json()
    assert txn["type"] == "ELECTRICITY"
    assert txn["status"] == "PROCESSING"

    status = wait_for_status(client, token, txn["id"])
    assert status == "SUCCESS"

    assert client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"] == 200000

    receipt = client.get(f"{API}/transactions/{txn['id']}/receipt", headers=auth_headers(token))
    assert receipt.status_code == 200
    assert receipt.json()["status"] == "SUCCESS"
    assert receipt.json()["meter_number"] == "1234567890"

    events = client.get(
        f"{API}/transactions/{txn['id']}/events", headers=auth_headers(token)
    ).json()
    types = [e["event_type"] for e in events]
    assert types == [
        "TRANSACTION_CREATED",
        "TRANSACTION_PENDING",
        "TRANSACTION_PROCESSING",
        "TRANSACTION_SUCCESS",
    ]


def test_wrong_pin_rejected(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 300000)
    vtoken = _validate(client, token)
    r = client.post(
        f"{API}/bill-payments/electricity/confirm",
        headers=auth_headers(token),
        json={"validation_token": vtoken, "amount": 100000, "pin": "0000"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_PIN"


def test_insufficient_balance_rejected(client):
    user = register_active_user(client)
    token = user["access_token"]
    vtoken = _validate(client, token)
    r = client.post(
        f"{API}/bill-payments/electricity/confirm",
        headers=auth_headers(token),
        json={"validation_token": vtoken, "amount": 100000, "pin": "1234"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_BALANCE"


def test_provider_declined_does_not_debit(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 300000)
    vtoken = _validate(client, token, meter="1239999")  # meters ending 9999 are declined
    r = client.post(
        f"{API}/bill-payments/electricity/confirm",
        headers=auth_headers(token),
        json={"validation_token": vtoken, "amount": 100000, "pin": "1234"},
    )
    assert r.status_code == 200
    txn = r.json()
    status = wait_for_status(client, token, txn["id"])
    assert status == "FAILED"
    # No debit occurred.
    assert client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"] == 300000


def test_confirm_is_idempotent(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 300000)
    vtoken = _validate(client, token)
    headers = {**auth_headers(token), "Idempotency-Key": "elec-dup-1"}
    first = client.post(
        f"{API}/bill-payments/electricity/confirm",
        headers=headers,
        json={"validation_token": vtoken, "amount": 100000, "pin": "1234"},
    )
    second = client.post(
        f"{API}/bill-payments/electricity/confirm",
        headers=headers,
        json={"validation_token": vtoken, "amount": 100000, "pin": "1234"},
    )
    assert first.json()["id"] == second.json()["id"]

    wait_for_status(client, token, first.json()["id"])
    # Only one debit despite two confirm calls.
    assert client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"] == 200000
