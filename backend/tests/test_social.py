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
    assert req.json()["transaction_id"]
    assert req.json()["payer_transaction_id"]

    # Both parties see PENDING history rows immediately.
    alice_txns = client.get(
        f"{API}/transactions?limit=20", headers=auth_headers(alice["access_token"])
    ).json()
    bob_txns = client.get(
        f"{API}/transactions?limit=20", headers=auth_headers(bob["access_token"])
    ).json()
    alice_pending = next(t for t in alice_txns if t["id"] == req.json()["transaction_id"])
    bob_pending = next(t for t in bob_txns if t["id"] == req.json()["payer_transaction_id"])
    assert alice_pending["status"] == "PENDING"
    assert alice_pending["type"] == "MONEY_REQUEST_OUT"
    assert bob_pending["status"] == "PENDING"
    assert bob_pending["type"] == "MONEY_REQUEST_IN"

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
    assert paid.json()["funding_mode"] == "WALLET"
    assert paid.json()["transaction_id"]
    assert paid.json()["requester"]["phone"] == alice["phone"]
    assert paid.json()["payer"]["phone"] == bob["phone"]
    assert paid.json()["requester"]["name"]
    assert paid.json()["payer"]["name"]

    # Outgoing list for requester must flip immediately.
    outgoing = client.get(
        f"{API}/money-requests?direction=outgoing",
        headers=auth_headers(alice["access_token"]),
    ).json()
    alice_req = next(r for r in outgoing if r["id"] == rid)
    assert alice_req["status"] == "PAID"

    assert _balance(client, bob["access_token"]) == 230000
    assert _balance(client, alice["access_token"]) == 70000

    # Settled history stays request to/from (not SEND_MONEY / TRANSFER_RECEIVED).
    alice_paid = client.get(
        f"{API}/transactions/{req.json()['transaction_id']}",
        headers=auth_headers(alice["access_token"]),
    ).json()
    bob_paid = client.get(
        f"{API}/transactions/{req.json()['payer_transaction_id']}",
        headers=auth_headers(bob["access_token"]),
    ).json()
    assert alice_paid["type"] == "MONEY_REQUEST_OUT"
    assert alice_paid["status"] == "SUCCESS"
    assert alice_paid["description"].startswith("Request to ")
    assert bob_paid["type"] == "MONEY_REQUEST_IN"
    assert bob_paid["status"] == "SUCCESS"
    assert bob_paid["description"].startswith("Request from ")

    notifs = client.get(f"{API}/notifications", headers=auth_headers(alice["access_token"])).json()
    assert any(n["type"] == "MONEY_REQUEST_PAID" for n in notifs)
    assert any(n["type"] == "TRANSFER_RECEIVED" for n in notifs)


def test_pay_insufficient_without_campay_fails(client):
    from unittest.mock import patch

    import app.integrations.campay as campay_mod

    alice = register_active_user(client)
    bob = register_active_user(client)
    # Bob has no funds and Campay is mocked off → INSUFFICIENT_BALANCE.
    rid = client.post(
        f"{API}/money-requests",
        headers=auth_headers(alice["access_token"]),
        json={"payer": bob["phone"], "amount": 10000},
    ).json()["id"]
    with patch.object(campay_mod, "campay_configured", return_value=False):
        r = client.post(
            f"{API}/money-requests/{rid}/pay",
            headers=auth_headers(bob["access_token"]),
            json={"pin": "1234"},
        )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert _balance(client, alice["access_token"]) == 0


def test_pay_via_campay_then_reconcile_credits_requester(client):
    from unittest.mock import MagicMock, patch

    import app.integrations.campay as campay_mod

    alice = register_active_user(client)
    bob = register_active_user(client)
    # Bob underfunded so pay branches to Campay.
    _fund(client, bob["access_token"], 1000)
    rid = client.post(
        f"{API}/money-requests",
        headers=auth_headers(alice["access_token"]),
        json={"payer": bob["phone"], "amount": 50000},
    ).json()["id"]

    campay_ref = "mr-campay-1111-2222-4333-844455555555"
    mock_client = MagicMock()
    mock_client.collect.return_value = {
        "reference": campay_ref,
        "status": "PENDING",
        "ussd_code": "*126#",
        "operator": "MTN",
    }
    mock_client.get_transaction.return_value = {
        "reference": campay_ref,
        "status": "SUCCESSFUL",
        "amount": "500.00",
        "currency": "XAF",
        "operator": "MTN",
        "operator_reference": "op-mr-1",
        "external_reference": "ext",
        "phone_number": "237650001234",
        "reason": "",
        "endpoint": "collect",
    }

    with patch.object(campay_mod, "campay_configured", return_value=True), patch.object(
        campay_mod, "get_campay_client", return_value=mock_client
    ):
        paid = client.post(
            f"{API}/money-requests/{rid}/pay",
            headers=auth_headers(bob["access_token"]),
            json={"pin": "1234", "phone": "+237650001234"},
        )
    assert paid.status_code == 200, paid.text
    body = paid.json()
    assert body["status"] == "PROCESSING"
    assert body["funding_mode"] == "CAMPAY"
    assert body["collect_transaction_id"]
    assert _balance(client, alice["access_token"]) == 0
    assert _balance(client, bob["access_token"]) == 1000

    with patch.object(campay_mod, "campay_configured", return_value=True), patch.object(
        campay_mod, "get_campay_client", return_value=mock_client
    ), patch(
        "app.services.reconciliation_service._is_campay_txn", return_value=True
    ):
        from app.db.database import SessionLocal
        from app.services.reconciliation_service import reconcile_pending

        db = SessionLocal()
        try:
            settled = reconcile_pending(db, min_age_seconds=0)
        finally:
            db.close()
        assert settled >= 1

    assert _balance(client, alice["access_token"]) == 50000
    # Payer FinPay balance unchanged — MoMo funded the credit to Alice.
    assert _balance(client, bob["access_token"]) == 1000
    outgoing = client.get(
        f"{API}/money-requests?direction=outgoing",
        headers=auth_headers(alice["access_token"]),
    ).json()
    assert next(r for r in outgoing if r["id"] == rid)["status"] == "PAID"


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


def test_request_by_phone_variants(client):
    """Payer lookup must accept common phone formats, not only exact DB string."""
    alice = register_active_user(client)
    bob = register_active_user(client)
    digits = "".join(c for c in bob["phone"] if c.isdigit())  # 2376xxxxxxxx
    local = digits[3:]  # 6xxxxxxxx

    for payer in (bob["phone"], digits, local, "0" + local, f"+{digits}"):
        r = client.post(
            f"{API}/money-requests",
            headers=auth_headers(alice["access_token"]),
            json={"payer": payer, "amount": 1000},
        )
        assert r.status_code == 200, f"payer={payer!r} -> {r.status_code} {r.text}"
        assert r.json()["payer_id"]
        # Cancel so the next variant can create another pending request.
        client.post(
            f"{API}/money-requests/{r.json()['id']}/cancel",
            headers=auth_headers(alice["access_token"]),
        )
