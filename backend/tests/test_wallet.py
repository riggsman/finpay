from app.core.config import settings

from .conftest import SAMPLE_BANK_DETAILS, SAMPLE_CARD_DETAILS, auth_headers, register_active_user

API = settings.API_V1_PREFIX


def test_add_money_credits_wallet(client):
    user = register_active_user(client)
    h = auth_headers(user["access_token"])

    assert client.get(f"{API}/wallet", headers=h).json()["balance"] == 0

    r = client.post(
        f"{API}/wallet/add-money",
        headers=h,
        json={
            "amount": 25000,
            "funding_method": "card",
            "card_details": SAMPLE_CARD_DETAILS,
        },
    )
    assert r.status_code == 200
    assert r.json()["status"] == "SUCCESS"
    assert "****1111" in (r.json().get("description") or "")

    assert client.get(f"{API}/wallet", headers=h).json()["balance"] == 25000

    notifs = client.get(f"{API}/notifications", headers=h).json()
    assert any(n["type"] == "WALLET_CREDITED" for n in notifs)


def test_add_money_is_idempotent(client):
    user = register_active_user(client)
    h = {**auth_headers(user["access_token"]), "Idempotency-Key": "dup-key-1"}
    payload = {
        "amount": 10000,
        "funding_method": "card",
        "card_details": SAMPLE_CARD_DETAILS,
    }

    first = client.post(f"{API}/wallet/add-money", headers=h, json=payload)
    second = client.post(f"{API}/wallet/add-money", headers=h, json=payload)

    assert first.json()["id"] == second.json()["id"]
    balance = client.get(
        f"{API}/wallet", headers=auth_headers(user["access_token"])
    ).json()["balance"]
    assert balance == 10000


def test_add_money_card_requires_details(client):
    user = register_active_user(client)
    h = auth_headers(user["access_token"])
    r = client.post(
        f"{API}/wallet/add-money",
        headers=h,
        json={"amount": 10000, "funding_method": "card"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CARD_DETAILS_REQUIRED"


def test_add_money_bank_with_details(client):
    user = register_active_user(client)
    h = auth_headers(user["access_token"])
    r = client.post(
        f"{API}/wallet/add-money",
        headers=h,
        json={
            "amount": 15000,
            "funding_method": "bank",
            "bank_details": SAMPLE_BANK_DETAILS,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SUCCESS"
    assert client.get(f"{API}/wallet", headers=h).json()["balance"] == 15000


def test_funding_flags_hide_and_block_methods(client, admin_token):
    from app.db.database import SessionLocal
    from app.models.fees import ServiceFlag

    user = register_active_user(client)
    h = auth_headers(user["access_token"])

    db = SessionLocal()
    try:
        for key in ("funding_card", "funding_bank"):
            flag = db.query(ServiceFlag).filter(ServiceFlag.key == key).one()
            flag.enabled = False
        db.commit()
    finally:
        db.close()

    cfg = client.get(f"{API}/config", headers=h).json()
    assert cfg["funding_methods"]["card"] is False
    assert cfg["funding_methods"]["bank"] is False
    assert cfg["funding_methods"]["mobile_money"] is True

    r = client.post(
        f"{API}/wallet/add-money",
        headers=h,
        json={
            "amount": 10000,
            "funding_method": "card",
            "card_details": SAMPLE_CARD_DETAILS,
        },
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SERVICE_DISABLED"
