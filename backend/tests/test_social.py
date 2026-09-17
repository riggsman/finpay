from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def _fund(client, token, amount):
    from .conftest import fund_wallet
    fund_wallet(client, token, amount)


def _balance(client, token):
    return client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]


# --- Beneficiaries ---------------------------------------------------------

def test_add_and_list_beneficiary(client):
    owner = register_active_user(client)
    friend = register_active_user(client)
    r = client.post(
        f"{API}/beneficiaries",
        headers=auth_headers(owner["access_token"]),
        json={"identifier": friend["phone"]},
    )
    assert r.status_code == 200
    assert r.json()["phone"] == friend["phone"]

    # Idempotent add.
    client.post(
        f"{API}/beneficiaries",
        headers=auth_headers(owner["access_token"]),
        json={"identifier": friend["phone"]},
    )
    lst = client.get(f"{API}/beneficiaries", headers=auth_headers(owner["access_token"])).json()
    assert len(lst) == 1


def test_add_self_beneficiary_rejected(client):
    owner = register_active_user(client)
    r = client.post(
        f"{API}/beneficiaries",
        headers=auth_headers(owner["access_token"]),
        json={"identifier": owner["phone"]},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SELF_BENEFICIARY"


def test_delete_beneficiary(client):
    owner = register_active_user(client)
    friend = register_active_user(client)
    bid = client.post(
        f"{API}/beneficiaries",
        headers=auth_headers(owner["access_token"]),
        json={"identifier": friend["phone"]},
    ).json()["id"]
    d = client.delete(f"{API}/beneficiaries/{bid}", headers=auth_headers(owner["access_token"]))
    assert d.status_code == 200
    lst = client.get(f"{API}/beneficiaries", headers=auth_headers(owner["access_token"])).json()
    assert lst == []


# --- Money requests --------------------------------------------------------

def test_request_and_pay_moves_funds(client):
    alice = register_active_user(client)
    bob = register_active_user(client)
    _fund(client, bob["access_token"], 300000)

    req = client.post(
        f"{API}/money-requests",
        headers=auth_headers(alice["access_token"]),
        json={"payer": bob["phone"], "amount": 70000, "note": "Lunch"},
    )
    assert req.status_code == 200
    rid = req.json()["id"]
    assert req.json()["status"] == "PENDING"

    # Bob sees it as incoming.
    incoming = client.get(
        f"{API}/money-requests?direction=incoming", headers=auth_headers(bob["access_token"])
    ).json()
    assert any(r["id"] == rid for r in incoming)

    paid = client.post(
        f"{API}/money-requests/{rid}/pay",
        headers=auth_headers(bob["access_token"]),
        json={"pin": "1234"},
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "PAID"
    assert paid.json()["transaction_id"]

    assert _balance(client, bob["access_token"]) == 230000
    assert _balance(client, alice["access_token"]) == 70000

    notifs = client.get(f"{API}/notifications", headers=auth_headers(alice["access_token"])).json()
    assert any(n["type"] == "MONEY_REQUEST_PAID" for n in notifs)
    assert any(n["type"] == "TRANSFER_RECEIVED" for n in notifs)


def test_pay_wrong_pin_rejected(client):
    alice = register_active_user(client)
    bob = register_active_user(client)
    _fund(client, bob["access_token"], 100000)
    rid = client.post(
        f"{API}/money-requests",
        headers=auth_headers(alice["access_token"]),
        json={"payer": bob["phone"], "amount": 10000},
    ).json()["id"]
    r = client.post(
        f"{API}/money-requests/{rid}/pay",
        headers=auth_headers(bob["access_token"]),
        json={"pin": "0000"},
    )
    assert r.status_code == 401
    # No charge occurred.
    assert _balance(client, bob["access_token"]) == 100000


def test_cannot_pay_twice(client):
    alice = register_active_user(client)
    bob = register_active_user(client)
    _fund(client, bob["access_token"], 100000)
    rid = client.post(
        f"{API}/money-requests",
        headers=auth_headers(alice["access_token"]),
        json={"payer": bob["phone"], "amount": 10000},
    ).json()["id"]
    client.post(f"{API}/money-requests/{rid}/pay",
                headers=auth_headers(bob["access_token"]), json={"pin": "1234"})
    again = client.post(f"{API}/money-requests/{rid}/pay",
                        headers=auth_headers(bob["access_token"]), json={"pin": "1234"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "REQUEST_NOT_PENDING"


def test_decline_and_cancel(client):
    alice = register_active_user(client)
    bob = register_active_user(client)

    rid = client.post(
        f"{API}/money-requests",
        headers=auth_headers(alice["access_token"]),
        json={"payer": bob["phone"], "amount": 10000},
    ).json()["id"]
    declined = client.post(
        f"{API}/money-requests/{rid}/decline", headers=auth_headers(bob["access_token"])
    )
    assert declined.json()["status"] == "DECLINED"

    rid2 = client.post(
        f"{API}/money-requests",
        headers=auth_headers(alice["access_token"]),
        json={"payer": bob["phone"], "amount": 5000},
    ).json()["id"]
    cancelled = client.post(
        f"{API}/money-requests/{rid2}/cancel", headers=auth_headers(alice["access_token"])
    )
    assert cancelled.json()["status"] == "CANCELLED"


def test_request_from_self_rejected(client):
    alice = register_active_user(client)
    r = client.post(
        f"{API}/money-requests",
        headers=auth_headers(alice["access_token"]),
        json={"payer": alice["phone"], "amount": 1000},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "SELF_REQUEST"
