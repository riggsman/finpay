from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


def test_add_money_credits_wallet(client):
    user = register_active_user(client)
    h = auth_headers(user["access_token"])

    assert client.get(f"{API}/wallet", headers=h).json()["balance"] == 0

    r = client.post(f"{API}/wallet/add-money", headers=h, json={"amount": 25000})
    assert r.status_code == 200
    assert r.json()["status"] == "SUCCESS"

    assert client.get(f"{API}/wallet", headers=h).json()["balance"] == 25000

    notifs = client.get(f"{API}/notifications", headers=h).json()
    assert any(n["type"] == "WALLET_CREDITED" for n in notifs)


def test_add_money_is_idempotent(client):
    user = register_active_user(client)
    h = {**auth_headers(user["access_token"]), "Idempotency-Key": "dup-key-1"}

    first = client.post(f"{API}/wallet/add-money", headers=h, json={"amount": 10000})
    second = client.post(f"{API}/wallet/add-money", headers=h, json={"amount": 10000})

    assert first.json()["id"] == second.json()["id"]
    # Balance reflects a single credit, not two.
    balance = client.get(
        f"{API}/wallet", headers=auth_headers(user["access_token"])
    ).json()["balance"]
    assert balance == 10000
