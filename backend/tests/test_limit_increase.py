from app.core.config import settings

from .conftest import auth_headers, fund_wallet, register_active_user

API = settings.API_V1_PREFIX


def test_limit_increase_request_approve_and_enforce(client, admin_token):
    user = register_active_user(client)
    token = user["access_token"]

    # Raise platform defaults stay at 500,000 XAF; request higher.
    created = client.post(
        f"{API}/me/security/limit-requests",
        headers=auth_headers(token),
        json={
            "requested_per_txn_limit": 100_000_00,  # 100,000.00 — still below default 500k
            "requested_daily_limit": 100_000_00,
            "reason": "Need more",
        },
    )
    # 100k < 500k default → rejected as too low
    assert created.status_code == 422

    created = client.post(
        f"{API}/me/security/limit-requests",
        headers=auth_headers(token),
        json={
            "requested_per_txn_limit": 1_000_000_00,  # 1,000,000.00
            "requested_daily_limit": 2_000_000_00,
            "reason": "Business volume",
        },
    )
    assert created.status_code == 200
    req_id = created.json()["id"]

    approved = client.post(
        f"{API}/admin/limit-requests/{req_id}/approve",
        headers=auth_headers(admin_token),
        json={
            "approved_per_txn_limit": 800_000_00,
            "approved_daily_limit": 1_500_000_00,
            "duration_days": 7,
            "spending_cap": 900_000_00,
        },
    )
    assert approved.status_code == 200

    notifs = client.get(f"{API}/notifications", headers=auth_headers(token)).json()
    approved_n = next((n for n in notifs if n["type"] == "LIMIT_INCREASE_APPROVED"), None)
    assert approved_n is not None
    assert "raised" in approved_n["message"].lower()
    assert approved_n["priority"] == "HIGH"

    limits = client.get(f"{API}/me/security/limits", headers=auth_headers(token)).json()
    assert limits["per_txn_limit"] == 800_000_00
    assert limits["active_grant"] is not None

    # Over per-txn raised limit → clear refusal
    fund_wallet(client, token, 50_000_000_00)
    over = client.post(
        f"{API}/wallet/withdraw",
        headers=auth_headers(token),
        json={"amount": 900_000_00, "destination": "Bank", "pin": "1234"},
    )
    assert over.status_code == 422
    assert over.json()["error"]["code"] == "PER_TXN_LIMIT_EXCEEDED"
    assert "per-transaction limit" in over.json()["error"]["message"].lower()


def test_limit_increase_reject_notifies(client, admin_token):
    user = register_active_user(client)
    token = user["access_token"]
    created = client.post(
        f"{API}/me/security/limit-requests",
        headers=auth_headers(token),
        json={
            "requested_per_txn_limit": 1_000_000_00,
            "requested_daily_limit": 2_000_000_00,
            "reason": "Travel",
        },
    ).json()
    rejected = client.post(
        f"{API}/admin/limit-requests/{created['id']}/reject",
        headers=auth_headers(admin_token),
        json={"reason": "Insufficient account history."},
    )
    assert rejected.status_code == 200
    notifs = client.get(f"{API}/notifications", headers=auth_headers(token)).json()
    assert any(n["type"] == "LIMIT_INCREASE_REJECTED" for n in notifs)
