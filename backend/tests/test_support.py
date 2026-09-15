from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def _create_ticket(client, token):
    return client.post(
        f"{API}/support/tickets",
        headers=auth_headers(token),
        json={"subject": "Card declined", "category": "payments", "message": "It failed twice."},
    )


def test_create_ticket_adds_agent_ack(client):
    user = register_active_user(client)
    token = user["access_token"]
    r = _create_ticket(client, token)
    assert r.status_code == 200
    assert r.json()["status"] == "IN_PROGRESS"

    detail = client.get(
        f"{API}/support/tickets/{r.json()['id']}", headers=auth_headers(token)
    ).json()
    senders = [m["sender"] for m in detail["messages"]]
    assert senders == ["user", "agent"]

    notifs = client.get(f"{API}/notifications", headers=auth_headers(token)).json()
    assert any(n["type"] == "SUPPORT_TICKET_UPDATE" for n in notifs)


def test_reply_and_close_ticket(client):
    user = register_active_user(client)
    token = user["access_token"]
    tid = _create_ticket(client, token).json()["id"]

    reply = client.post(
        f"{API}/support/tickets/{tid}/messages",
        headers=auth_headers(token),
        json={"body": "Any update?"},
    )
    assert reply.status_code == 200
    assert reply.json()["sender"] == "user"

    closed = client.post(f"{API}/support/tickets/{tid}/close", headers=auth_headers(token))
    assert closed.json()["status"] == "CLOSED"


def test_ticket_ownership_enforced(client):
    owner = register_active_user(client)
    other = register_active_user(client)
    tid = _create_ticket(client, owner["access_token"]).json()["id"]
    r = client.get(f"{API}/support/tickets/{tid}", headers=auth_headers(other["access_token"]))
    assert r.status_code == 404


def _make_transaction(client, token):
    client.post(f"{API}/wallet/add-money", headers=auth_headers(token), json={"amount": 10000})
    return client.get(f"{API}/transactions?limit=1", headers=auth_headers(token)).json()[0]["id"]


def test_create_dispute(client):
    user = register_active_user(client)
    token = user["access_token"]
    tid = _make_transaction(client, token)
    r = client.post(
        f"{API}/support/disputes?transaction_id={tid}",
        headers=auth_headers(token),
        json={"reason": "unauthorized", "description": "Not me."},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "OPEN"
    assert r.json()["transaction_id"] == tid


def test_duplicate_dispute_rejected(client):
    user = register_active_user(client)
    token = user["access_token"]
    tid = _make_transaction(client, token)
    first = client.post(
        f"{API}/support/disputes?transaction_id={tid}",
        headers=auth_headers(token), json={"reason": "unauthorized"},
    )
    assert first.status_code == 200
    second = client.post(
        f"{API}/support/disputes?transaction_id={tid}",
        headers=auth_headers(token), json={"reason": "unauthorized"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DISPUTE_EXISTS"


def test_dispute_requires_owned_transaction(client):
    user = register_active_user(client)
    r = client.post(
        f"{API}/support/disputes?transaction_id=999999",
        headers=auth_headers(user["access_token"]), json={"reason": "x"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"
