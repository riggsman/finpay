from types import SimpleNamespace

from app.core.config import settings
from app.notifications import email as email_channel

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX


# --- Providers -------------------------------------------------------------

def test_providers_seeded_and_listed(client, admin_token):
    rows = client.get(f"{API}/admin/providers", headers=auth_headers(admin_token)).json()
    keys = {(p["category"], p["provider_id"]) for p in rows}
    assert ("electricity", "eneo") in keys
    assert ("airtime", "mtn") in keys and ("data", "orange") in keys


def test_add_provider_and_front_store(client, admin_token):
    created = client.post(f"{API}/admin/providers", headers=auth_headers(admin_token),
                          json={"category": "electricity", "provider_id": "aes", "name": "AES Sonel"})
    assert created.status_code == 200
    user = register_active_user(client)
    names = [p["name"] for p in client.get(
        f"{API}/bill-payments/providers?category=electricity",
        headers=auth_headers(user["access_token"])).json()["providers"]]
    assert "AES Sonel" in names and "ENEO" in names


def test_add_custom_category_provider_without_code_change(client, admin_token):
    """Admins can onboard a brand-new category + provider from Back Office."""
    created = client.post(
        f"{API}/admin/providers",
        headers=auth_headers(admin_token),
        json={
            "category": "cable_tv",
            "provider_id": "canalplus",
            "name": "Canal+",
            "flow": "direct_topup",
            "integration_mode": "HTTP",
            "base_url": "https://api.canal.example/v1",
            "target_label": "Decoder number",
            "config": {"api_key_ref": "CANAL_KEY", "timeout_seconds": 20},
            "icon": "📺",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["category"] == "cable_tv"
    assert body["flow"] == "direct_topup"
    assert body["integration_mode"] == "HTTP"
    assert body["config"]["api_key_ref"] == "CANAL_KEY"

    # Front-store service tile + fee rule are auto-created.
    services = client.get(f"{API}/admin/services", headers=auth_headers(admin_token)).json()
    assert any(s["key"] == "cable_tv" and s["kind"] == "service" for s in services)
    fees = client.get(f"{API}/admin/fees", headers=auth_headers(admin_token)).json()
    assert any(f["operation"] == "CABLE_TV" for f in fees)

    user = register_active_user(client)
    providers = client.get(
        f"{API}/bill-payments/topup/providers?category=cable_tv",
        headers=auth_headers(user["access_token"]),
    ).json()["providers"]
    assert any(p["id"] == "canalplus" and p["target_label"] == "Decoder number" for p in providers)


def test_disable_provider_hides_from_front_store(client, admin_token):
    rows = client.get(f"{API}/admin/providers", headers=auth_headers(admin_token)).json()
    eneo = next(p for p in rows if p["category"] == "electricity" and p["provider_id"] == "eneo")
    client.put(f"{API}/admin/providers/{eneo['id']}", headers=auth_headers(admin_token),
               json={"enabled": False})
    user = register_active_user(client)
    names = [p["provider_id"] for p in client.get(
        f"{API}/bill-payments/providers?category=electricity",
        headers=auth_headers(user["access_token"])).json()["providers"]]
    assert "eneo" not in names


def test_duplicate_provider_rejected(client, admin_token):
    r = client.post(f"{API}/admin/providers", headers=auth_headers(admin_token),
                    json={"category": "electricity", "provider_id": "eneo", "name": "Dup"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PROVIDER_EXISTS"


# --- Settings --------------------------------------------------------------

def test_settings_listed_and_updated(client, admin_token):
    rows = client.get(f"{API}/admin/settings", headers=auth_headers(admin_token)).json()
    keys = {s["key"] for s in rows}
    assert {
        "default_per_txn_limit",
        "default_daily_limit",
        "email_notifications_enabled",
    } <= keys

    u = client.put(f"{API}/admin/settings", headers=auth_headers(admin_token),
                   json={"values": {"email_from_name": "PayCo"}})
    assert u.status_code == 200
    rows2 = client.get(f"{API}/admin/settings", headers=auth_headers(admin_token)).json()
    assert next(s for s in rows2 if s["key"] == "email_from_name")["value"] == "PayCo"


def test_default_limit_setting_applied_to_new_user(client, admin_token):
    client.put(f"{API}/admin/settings", headers=auth_headers(admin_token),
               json={"values": {"default_per_txn_limit": "7500000"}})
    user = register_active_user(client)
    limits = client.get(f"{API}/me/security/limits", headers=auth_headers(user["access_token"])).json()
    assert limits["per_txn_limit"] == 7500000


def test_admin_limit_settings_apply_to_existing_users(client, admin_token):
    user = register_active_user(client)
    token = user["access_token"]
    client.put(
        f"{API}/admin/settings",
        headers=auth_headers(admin_token),
        json={"values": {"default_per_txn_limit": "1234500", "default_daily_limit": "9876500"}},
    )
    limits = client.get(f"{API}/me/security/limits", headers=auth_headers(token)).json()
    assert limits["per_txn_limit"] == 1234500
    assert limits["daily_limit"] == 9876500


# --- Email -----------------------------------------------------------------

def test_email_console_send_records(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "console")
    email_channel.sent_log.clear()
    assert email_channel.send_email("user@example.com", "Sub", "Body") is True
    assert email_channel.sent_log[-1]["to"] == "user@example.com"


def test_email_disabled_backend(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "disabled")
    assert email_channel.send_email("user@example.com", "s", "b") is False


def test_resolve_email_eligibility(client, admin_token):
    user = register_active_user(client)
    me = client.get(f"{API}/me", headers=auth_headers(user["access_token"])).json()
    high = SimpleNamespace(
        user_id=me["id"], priority="HIGH", title="T", message="M", type="WALLET_CREDITED", data=None,
    )
    normal = SimpleNamespace(
        user_id=me["id"], priority="NORMAL", title="T", message="M", type="WALLET_CREDITED", data=None,
    )

    assert email_channel.resolve_email(high) is not None
    # NORMAL priority is below the email threshold.
    assert email_channel.resolve_email(normal) is None

    # Disabling the setting suppresses email.
    client.put(f"{API}/admin/settings", headers=auth_headers(admin_token),
               json={"values": {"email_notifications_enabled": "false"}})
    assert email_channel.resolve_email(high) is None


def test_per_service_email_toggle(client, admin_token):
    user = register_active_user(client)
    me = client.get(f"{API}/me", headers=auth_headers(user["access_token"])).json()
    deposit = SimpleNamespace(
        user_id=me["id"],
        priority="HIGH",
        title="Money Added",
        message="Funds received",
        type="WALLET_CREDITED",
        data=None,
    )
    assert email_channel.resolve_email(deposit) is not None

    r = client.put(
        f"{API}/admin/services/add_money",
        headers=auth_headers(admin_token),
        json={"email_enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["email_enabled"] is False
    assert email_channel.resolve_email(deposit) is None

    # Other services still email when their flag is on.
    transfer = SimpleNamespace(
        user_id=me["id"],
        priority="HIGH",
        title="Transfer Sent",
        message="Sent",
        type="TRANSFER_SENT",
        data=None,
    )
    assert email_channel.resolve_email(transfer) is not None


def test_admin_email_test_endpoint(client, admin_token):
    r = client.post(f"{API}/admin/email/test", headers=auth_headers(admin_token),
                    json={"subject": "Hi", "body": "There"})
    assert r.status_code == 200
    assert r.json()["sent"] is True
    assert r.json()["to"] == settings.ADMIN_EMAIL
