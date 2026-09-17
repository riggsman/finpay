"""Campay mobile money: client helpers, deposit/withdraw, admin test APIs."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.integrations.campay import (
    is_campay_reference,
    map_campay_status,
    minor_to_campay_amount,
    normalize_msisdn,
    reset_campay_client,
)
from app.integrations import campay as campay_mod

from .conftest import auth_headers, register_active_user, wait_for_status

API = settings.API_V1_PREFIX


@pytest.fixture(autouse=True)
def _reset_campay():
    reset_campay_client()
    yield
    reset_campay_client()


def _fund(client, token, amount):
    from .conftest import fund_wallet
    fund_wallet(client, token, amount)


def test_normalize_msisdn_and_amount():
    assert normalize_msisdn("+237650001234") == "237650001234"
    assert normalize_msisdn("650001234") == "237650001234"
    assert minor_to_campay_amount(100000) == 1000
    with pytest.raises(Exception):
        minor_to_campay_amount(1050)
    assert is_campay_reference("bcedde9b-62a7-4421-96ac-2e6179552a1a")
    assert not is_campay_reference("prov_abc123")
    assert map_campay_status("SUCCESSFUL") == "SUCCESS"
    assert map_campay_status("FAILED") == "FAILED"
    assert map_campay_status("PENDING") == "PENDING"


def test_admin_campay_status_unconfigured(client, admin_token):
    with patch.object(type(settings), "campay_configured", property(lambda self: False)):
        r = client.get(f"{API}/admin/campay/status", headers=auth_headers(admin_token))
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["credentials_ready"] is False
    assert "payment_mode" in body
    assert "wallet_campay_enabled" in body
    assert "reconcile_worker_enabled" in body


def test_admin_campay_balance_requires_config(client, admin_token):
    with patch("app.routers.campay_admin.campay_credentials_ready", return_value=False), patch.object(
        type(settings), "campay_configured", property(lambda self: False)
    ):
        r = client.get(f"{API}/admin/campay/balance", headers=auth_headers(admin_token))
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "CAMPAY_NOT_CONFIGURED"


def test_admin_campay_test_token_mocked(client, admin_token):
    mock_client = MagicMock()
    mock_client.get_token.return_value = "tok_abcdef012345"
    with patch.object(campay_mod, "campay_credentials_ready", return_value=True), patch.object(
        campay_mod, "get_campay_client", return_value=mock_client
    ), patch("app.routers.campay_admin.campay_credentials_ready", return_value=True), patch(
        "app.routers.campay_admin.get_campay_client", return_value=mock_client
    ), patch("app.routers.campay_admin.reset_campay_client"):
        r = client.post(f"{API}/admin/campay/test/token", headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_admin_sandbox_works_without_live_mode(client, admin_token):
    """Credentials alone unlock sandbox; PAYMENT_MODE=simulated does not block it."""
    mock_client = MagicMock()
    mock_client.get_balance.return_value = {
        "total_balance": "1000",
        "currency": "XAF",
        "mtn_balance": "500",
        "orange_balance": "500",
    }
    with patch("app.routers.campay_admin.campay_credentials_ready", return_value=True), patch(
        "app.routers.campay_admin.get_campay_client", return_value=mock_client
    ), patch.object(type(settings), "payment_mode", property(lambda self: "simulated")), patch.object(
        type(settings), "payments_live", property(lambda self: False)
    ):
        r = client.get(f"{API}/admin/campay/balance", headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["total_balance"] == "1000"


def test_webhook_acks_orphan_without_wallet_txn(client):
    """Admin/sandbox Campay refs must ACK so Campay does not retry forever."""
    import uuid

    ref = str(uuid.uuid4())
    from app.db.database import SessionLocal
    from app.services import campay_payment_service

    db = SessionLocal()
    try:
        campay_payment_service.record_initiate(
            db,
            reference=ref,
            endpoint="collect",
            user_id=None,
            transaction_id=None,
            external_reference=f"admin-test-orphan-{ref[:8]}",
            phone_number="237650001234",
            amount_minor=10000,
        )
        db.commit()
    finally:
        db.close()

    with patch("app.routers.campay_admin._verify_webhook_signature", return_value=None):
        r = client.post(
            f"{API}/webhooks/campay",
            json={"reference": ref, "status": "PENDING"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["wallet_txn"] is False


def test_card_deposit_still_instant_without_campay(client):
    user = register_active_user(client)
    token = user["access_token"]
    with patch.object(campay_mod, "campay_configured", return_value=False):
        r = client.post(
            f"{API}/wallet/add-money",
            headers=auth_headers(token),
            json={
                "amount": 50000,
                "funding_method": "card",
                "card_details": {
                    "card_number": "4111111111111111",
                    "card_holder": "Test User",
                    "expiry_month": 12,
                    "expiry_year": 2030,
                    "cvv": "123",
                },
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SUCCESS"
    bal = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    assert bal == 50000


def test_momo_deposit_pending_then_reconcile_success(client):
    user = register_active_user(client)
    token = user["access_token"]
    campay_ref = "11111111-2222-4333-8444-555555555555"

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
        "amount": "1000.00",
        "currency": "XAF",
        "operator": "MTN",
        "operator_reference": "op-1",
        "external_reference": "ext",
        "phone_number": "237650001234",
        "reason": "",
        "endpoint": "collect",
    }

    with patch.object(campay_mod, "campay_configured", return_value=True), patch.object(
        campay_mod, "get_campay_client", return_value=mock_client
    ), patch(
        "app.services.wallet_service._use_campay_for_deposit", return_value=True
    ):
        r = client.post(
            f"{API}/wallet/add-money",
            headers={**auth_headers(token), "Idempotency-Key": "campay-dep-1"},
            json={
                "amount": 100000,
                "funding_method": "mobile_money",
                "phone": "+237650001234",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PENDING"
    assert body["provider_reference"] == campay_ref
    before = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    assert before == 0

    with patch.object(campay_mod, "campay_configured", return_value=True), patch.object(
        campay_mod, "get_campay_client", return_value=mock_client
    ), patch(
        "app.services.reconciliation_service._is_campay_txn", return_value=True
    ):
        from app.db.database import SessionLocal
        from app.models.campay import CampayPayment
        from app.services.reconciliation_service import reconcile_pending

        db = SessionLocal()
        try:
            settled = reconcile_pending(db, min_age_seconds=0)
            row = db.query(CampayPayment).filter(CampayPayment.reference == campay_ref).one()
            assert row.status.upper() == "SUCCESSFUL" or row.mapped_status == "SUCCESS"
            assert row.operator == "MTN"
            assert row.phone_number == "237650001234"
            assert row.operator_reference == "op-1"
        finally:
            db.close()
        assert settled >= 1

    after = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    assert after == 100000
    txn = client.get(f"{API}/transactions/{body['id']}", headers=auth_headers(token)).json()
    assert txn["status"] == "SUCCESS"


def test_withdraw_failed_refunds(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    before = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]

    mock_client = MagicMock()
    mock_client.withdraw.return_value = {
        "reference": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        "status": "FAILED",
    }

    with patch("app.integrations.campay.campay_configured", return_value=True), patch(
        "app.integrations.campay.get_campay_client", return_value=mock_client
    ):
        r = client.post(
            f"{API}/wallet/withdraw",
            headers=auth_headers(token),
            json={"amount": 10000, "destination": "+237650001234", "pin": "1234"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "FAILED"
    after = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    assert after == before


def test_withdraw_success_campay(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    before = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]

    mock_client = MagicMock()
    mock_client.withdraw.return_value = {
        "reference": "aaaaaaaa-bbbb-4ccc-8ddd-ffffffffffff",
        "status": "SUCCESSFUL",
    }

    with patch("app.integrations.campay.campay_configured", return_value=True), patch(
        "app.integrations.campay.get_campay_client", return_value=mock_client
    ):
        r = client.post(
            f"{API}/wallet/withdraw",
            headers=auth_headers(token),
            json={"amount": 20000, "destination": "650001234", "pin": "1234"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SUCCESS"
    after = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    assert after == before - 20000


def test_admin_test_collect_mocked(client, admin_token):
    mock_client = MagicMock()
    mock_client.collect.return_value = {
        "reference": "cccccccc-dddd-4eee-8fff-000000000001",
        "status": "PENDING",
        "ussd_code": "*126#",
    }
    with patch("app.routers.campay_admin.campay_credentials_ready", return_value=True), patch(
        "app.routers.campay_admin.get_campay_client", return_value=mock_client
    ), patch("app.routers.campay_admin.normalize_msisdn", return_value="237650001234"):
        r = client.post(
            f"{API}/admin/campay/test/collect",
            headers=auth_headers(admin_token),
            json={"phone": "237650001234", "amount": 100},
        )
    assert r.status_code == 200, r.text
    assert r.json()["reference"]
    assert "does not credit" in r.json()["note"].lower()


def test_describe_provider_action_flags_credit_when_out_of_sync():
    from app.services.reconciliation_service import describe_provider_action

    action = describe_provider_action("SUCCESS", "PENDING", "ADD_MONEY")
    assert action["needs_reconciliation"] is True
    assert "credit" in action["action_required"].lower()
    assert action["action_label"]

    synced = describe_provider_action("SUCCESS", "SUCCESS", "ADD_MONEY")
    assert synced["needs_reconciliation"] is False


def test_admin_verify_then_reconcile_credits_user(client, admin_token):
    """When verify cannot auto-settle, reconcile credits wallet and updates status."""
    user = register_active_user(client)
    token = user["access_token"]
    campay_ref = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"

    mock_client = MagicMock()
    mock_client.collect.return_value = {
        "reference": campay_ref,
        "status": "PENDING",
        "ussd_code": "*126#",
    }
    mock_client.get_transaction.return_value = {
        "reference": campay_ref,
        "status": "SUCCESSFUL",
        "amount": "1000",
        "currency": "XAF",
        "operator": "MTN",
        "code": "00",
        "operator_reference": "op-recon-1",
        "external_reference": "",
        "phone_number": "237650001234",
        "reason": "",
        "endpoint": "collect",
    }

    with patch.object(campay_mod, "campay_configured", return_value=True), patch.object(
        campay_mod, "get_campay_client", return_value=mock_client
    ), patch(
        "app.services.wallet_service._use_campay_for_deposit", return_value=True
    ):
        created = client.post(
            f"{API}/wallet/add-money",
            headers={**auth_headers(token), "Idempotency-Key": "campay-recon-1"},
            json={
                "amount": 100000,
                "funding_method": "mobile_money",
                "phone": "+237650001234",
            },
        )
    assert created.status_code == 200, created.text
    txn_id = created.json()["id"]
    assert created.json()["status"] == "PENDING"

    before = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]

    with patch("app.integrations.campay.campay_credentials_ready", return_value=True), patch(
        "app.integrations.campay.get_campay_client", return_value=mock_client
    ), patch(
        "app.services.reconciliation_service.apply_campay_outcome", return_value=False
    ):
        verified = client.post(
            f"{API}/admin/transactions/{txn_id}/verify-provider",
            headers=auth_headers(admin_token),
        )
    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["provider_status"] == "SUCCESSFUL"
    assert body["mapped_status"] == "SUCCESS"
    assert body["finpay_status"] in ("PENDING", "PROCESSING", "CREATED")
    assert body["needs_reconciliation"] is True
    assert body["action_label"]
    assert body["settled"] is False

    with patch("app.integrations.campay.campay_credentials_ready", return_value=True), patch(
        "app.integrations.campay.get_campay_client", return_value=mock_client
    ):
        reconciled = client.post(
            f"{API}/admin/transactions/{txn_id}/reconcile",
            headers=auth_headers(admin_token),
        )
    assert reconciled.status_code == 200, reconciled.text
    out = reconciled.json()
    assert out["settled"] is True
    assert out["finpay_status"] == "SUCCESS"
    assert out["needs_reconciliation"] is False

    after = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    assert after == before + 100000
