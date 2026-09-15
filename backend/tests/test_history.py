from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def _setup_user_with_txns(client):
    user = register_active_user(client)
    token = user["access_token"]
    h = auth_headers(token)
    client.post(f"{API}/wallet/add-money", headers=h, json={"amount": 100000})
    client.post(f"{API}/wallet/add-money", headers=h, json={"amount": 50000})
    client.post(
        f"{API}/wallet/withdraw",
        headers=h,
        json={"amount": 30000, "destination": "Bank ****9", "pin": "1234"},
    )
    return token


def test_list_returns_all(client):
    token = _setup_user_with_txns(client)
    rows = client.get(f"{API}/transactions", headers=auth_headers(token)).json()
    assert len(rows) == 3


def test_filter_by_type(client):
    token = _setup_user_with_txns(client)
    rows = client.get(f"{API}/transactions?type=WITHDRAW", headers=auth_headers(token)).json()
    assert len(rows) == 1
    assert rows[0]["type"] == "WITHDRAW"


def test_filter_by_amount_range(client):
    token = _setup_user_with_txns(client)
    rows = client.get(
        f"{API}/transactions?amount_min=60000", headers=auth_headers(token)
    ).json()
    assert [r["amount"] for r in rows] == [100000]


def test_filter_by_status_and_type(client):
    token = _setup_user_with_txns(client)
    rows = client.get(
        f"{API}/transactions?status=SUCCESS&type=ADD_MONEY", headers=auth_headers(token)
    ).json()
    assert len(rows) == 2
    assert all(r["type"] == "ADD_MONEY" for r in rows)


def test_search_by_description(client):
    token = _setup_user_with_txns(client)
    rows = client.get(f"{API}/transactions?search=Bank", headers=auth_headers(token)).json()
    assert len(rows) == 1
    assert "Bank" in rows[0]["description"]


def test_pagination(client):
    token = _setup_user_with_txns(client)
    page1 = client.get(f"{API}/transactions?page=1&limit=2", headers=auth_headers(token)).json()
    page2 = client.get(f"{API}/transactions?page=2&limit=2", headers=auth_headers(token)).json()
    assert len(page1) == 2
    assert len(page2) == 1
    # Pages do not overlap.
    ids = {t["id"] for t in page1} | {t["id"] for t in page2}
    assert len(ids) == 3


def test_receipt_and_events_for_transaction(client):
    token = _setup_user_with_txns(client)
    withdrawal = client.get(
        f"{API}/transactions?type=WITHDRAW", headers=auth_headers(token)
    ).json()[0]
    tid = withdrawal["id"]

    events = client.get(
        f"{API}/transactions/{tid}/events", headers=auth_headers(token)
    ).json()
    assert [e["event_type"] for e in events][0] == "TRANSACTION_CREATED"
    assert events[-1]["new_status"] == "SUCCESS"

    receipt = client.get(f"{API}/transactions/{tid}/receipt", headers=auth_headers(token))
    assert receipt.status_code == 200
    assert receipt.json()["status"] == "SUCCESS"
