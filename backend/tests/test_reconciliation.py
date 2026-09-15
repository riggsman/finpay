from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def _fund(client, token, amount):
    client.post(f"{API}/wallet/add-money", headers=auth_headers(token), json={"amount": amount})


def _confirm(client, token, meter, amount=100000):
    vt = client.post(
        f"{API}/bill-payments/electricity/validate",
        headers=auth_headers(token),
        json={"provider_id": "eneo", "meter_number": meter},
    ).json()["validation_token"]
    return client.post(
        f"{API}/bill-payments/electricity/confirm",
        headers=auth_headers(token),
        json={"validation_token": vt, "amount": amount, "pin": "1234"},
    ).json()


def _balance(client, token):
    return client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]


def test_provider_timeout_stays_pending_not_failed(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 300000)

    txn = _confirm(client, token, "1234565555")  # ...5555 => provider timeout
    assert txn["status"] == "PENDING"
    assert txn["failure_reason"] is None
    # No debit while pending.
    assert _balance(client, token) == 300000


def test_reconcile_settles_success_and_debits(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 300000)
    txn = _confirm(client, token, "1234565555")

    res = client.post(f"{API}/transactions/reconcile", headers=auth_headers(token))
    assert res.status_code == 200
    assert res.json()["reconciled"] == 1

    settled = client.get(f"{API}/transactions/{txn['id']}", headers=auth_headers(token)).json()
    assert settled["status"] == "SUCCESS"
    assert settled["provider_reference"]
    assert _balance(client, token) == 200000

    events = client.get(
        f"{API}/transactions/{txn['id']}/events", headers=auth_headers(token)
    ).json()
    types = [e["event_type"] for e in events]
    assert "PROVIDER_TIMEOUT" in types
    assert types[-1] == "TRANSACTION_SUCCESS"


def test_reconcile_settles_failed_without_debit(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 300000)
    txn = _confirm(client, token, "1234564444")  # ...4444 => reconcile to FAILED
    assert txn["status"] == "PENDING"

    client.post(f"{API}/transactions/reconcile", headers=auth_headers(token))

    settled = client.get(f"{API}/transactions/{txn['id']}", headers=auth_headers(token)).json()
    assert settled["status"] == "FAILED"
    assert settled["failure_reason"]
    # Never charged on failure.
    assert _balance(client, token) == 300000


def test_reconcile_noop_when_nothing_pending(client):
    user = register_active_user(client)
    res = client.post(f"{API}/transactions/reconcile", headers=auth_headers(user["access_token"]))
    assert res.json()["reconciled"] == 0
