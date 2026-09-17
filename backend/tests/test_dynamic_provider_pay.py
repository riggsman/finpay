"""Dynamic provider fields + unified pay/validate checkout."""

from app.core.config import settings

from .conftest import auth_headers, register_active_user, wait_for_status

API = settings.API_V1_PREFIX


def _fund(client, token, amount):
    from .conftest import fund_wallet
    fund_wallet(client, token, amount)


def _field_map(fields):
    return {f["key"]: f for f in fields}


def test_seeded_providers_expose_fields_schema(client, admin_token):
    rows = client.get(f"{API}/admin/providers", headers=auth_headers(admin_token)).json()
    mtn = next(p for p in rows if p["category"] == "airtime" and p["provider_id"] == "mtn")
    eneo = next(p for p in rows if p["category"] == "electricity" and p["provider_id"] == "eneo")

    mtn_fields = _field_map(mtn["fields"])
    assert set(mtn_fields) == {"phone", "amount", "message"}
    assert mtn_fields["phone"]["enabled"] is True
    assert mtn_fields["phone"]["label"] == "Phone number"
    assert mtn_fields["amount"]["enabled"] is True
    assert mtn_fields["message"]["enabled"] is False

    eneo_fields = _field_map(eneo["fields"])
    assert eneo_fields["phone"]["label"] == "Meter number"
    assert eneo_fields["message"]["enabled"] is False

    user = register_active_user(client)
    listed = client.get(
        f"{API}/bill-payments/providers?category=airtime",
        headers=auth_headers(user["access_token"]),
    ).json()["providers"]
    front = next(p for p in listed if p["id"] == "mtn")
    assert "fields" in front
    assert _field_map(front["fields"])["phone"]["enabled"] is True


def test_admin_rejects_unknown_and_too_many_fields(client, admin_token):
    h = auth_headers(admin_token)
    rows = client.get(f"{API}/admin/providers", headers=h).json()
    mtn = next(p for p in rows if p["category"] == "airtime" and p["provider_id"] == "mtn")

    bad_key = client.put(
        f"{API}/admin/providers/{mtn['id']}",
        headers=h,
        json={
            "config": {
                "fields": [
                    {"key": "phone", "enabled": True, "required": True, "label": "Phone"},
                    {"key": "fax", "enabled": True, "required": False, "label": "Fax"},
                ]
            }
        },
    )
    assert bad_key.status_code == 422
    assert bad_key.json()["error"]["code"] == "INVALID_FIELD_KEY"

    too_many = client.put(
        f"{API}/admin/providers/{mtn['id']}",
        headers=h,
        json={
            "config": {
                "fields": [
                    {"key": "phone", "enabled": True, "required": True, "label": "Phone"},
                    {"key": "amount", "enabled": True, "required": True, "label": "Amount"},
                    {"key": "message", "enabled": True, "required": False, "label": "Note"},
                    {"key": "phone", "enabled": True, "required": True, "label": "Dup"},
                ]
            }
        },
    )
    assert too_many.status_code == 422
    assert too_many.json()["error"]["code"] in {"TOO_MANY_FIELDS", "DUPLICATE_FIELD_KEY"}


def test_enable_message_field_lands_on_transaction(client, admin_token):
    h = auth_headers(admin_token)
    rows = client.get(f"{API}/admin/providers", headers=h).json()
    mtn = next(p for p in rows if p["category"] == "airtime" and p["provider_id"] == "mtn")

    updated = client.put(
        f"{API}/admin/providers/{mtn['id']}",
        headers=h,
        json={
            "config": {
                "fields": [
                    {"key": "phone", "enabled": True, "required": True, "label": "Phone number"},
                    {"key": "amount", "enabled": True, "required": True, "label": "Amount"},
                    {"key": "message", "enabled": True, "required": False, "label": "Reference"},
                ]
            }
        },
    )
    assert updated.status_code == 200, updated.text
    assert _field_map(updated.json()["fields"])["message"]["enabled"] is True

    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    pay = client.post(
        f"{API}/bill-payments/pay",
        headers={**auth_headers(token), "Idempotency-Key": "msg-air-1"},
        json={
            "category": "airtime",
            "provider_id": "mtn",
            "phone": "+237650001234",
            "amount": 1000,
            "message": "Birthday gift",
            "pin": "1234",
        },
    )
    assert pay.status_code == 200, pay.text
    assert "Birthday gift" in pay.json()["description"]


def test_disabled_message_rejected_when_sent(client, admin_token):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    r = client.post(
        f"{API}/bill-payments/pay",
        headers=auth_headers(token),
        json={
            "category": "airtime",
            "provider_id": "mtn",
            "phone": "+237650001234",
            "amount": 1000,
            "message": "should fail",
            "pin": "1234",
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "FIELD_DISABLED"


def test_unified_pay_airtime_phone_amount(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 500000)
    before = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    r = client.post(
        f"{API}/bill-payments/pay",
        headers={**auth_headers(token), "Idempotency-Key": "pay-air-1"},
        json={
            "category": "airtime",
            "provider_id": "mtn",
            "phone": "+237650001234",
            "amount": 2500,
            "pin": "1234",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 2500
    after = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    assert after == before - 2500


def test_new_category_auto_tile_and_service_pay_path(client, admin_token):
    created = client.post(
        f"{API}/admin/providers",
        headers=auth_headers(admin_token),
        json={
            "category": "gas",
            "provider_id": "gazcam",
            "name": "GazCam",
            "flow": "direct_topup",
            "target_label": "Bottle ID",
            "icon": "🔥",
            "config": {
                "fields": [
                    {"key": "phone", "enabled": True, "required": True, "label": "Bottle ID"},
                    {"key": "amount", "enabled": True, "required": True, "label": "Amount"},
                    {"key": "message", "enabled": False, "required": False, "label": "Message"},
                ]
            },
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["target_label"] == "Bottle ID"
    assert _field_map(body["fields"])["phone"]["label"] == "Bottle ID"

    services = client.get(f"{API}/admin/services", headers=auth_headers(admin_token)).json()
    assert any(s["key"] == "gas" and s["kind"] == "service" and s["enabled"] for s in services)

    fees = client.get(f"{API}/admin/fees", headers=auth_headers(admin_token)).json()
    assert any(f["operation"] == "GAS" for f in fees)

    user = register_active_user(client)
    token = user["access_token"]
    front_services = client.get(f"{API}/services", headers=auth_headers(token)).json()["services"]
    gas_tile = next(s for s in front_services if s["id"] == "gas")
    assert gas_tile["enabled"] is True
    assert gas_tile.get("icon") == "🔥"

    providers = client.get(
        f"{API}/bill-payments/providers?category=gas",
        headers=auth_headers(token),
    ).json()["providers"]
    assert any(p["id"] == "gazcam" for p in providers)

    _fund(client, token, 200000)
    pay = client.post(
        f"{API}/bill-payments/pay",
        headers={**auth_headers(token), "Idempotency-Key": "gas-1"},
        json={
            "category": "gas",
            "provider_id": "gazcam",
            "phone": "BOTTLE-99",
            "amount": 5000,
            "pin": "1234",
        },
    )
    assert pay.status_code == 200, pay.text


def test_unified_validate_and_pay_electricity(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 300000)

    v = client.post(
        f"{API}/bill-payments/validate",
        headers=auth_headers(token),
        json={"category": "electricity", "provider_id": "eneo", "phone": "1234567890"},
    )
    assert v.status_code == 200, v.text
    assert v.json()["customer"]["meter_number"] == "1234567890"
    assert v.json()["provider"]["id"] == "eneo"
    token_val = v.json()["validation_token"]

    before = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    pay = client.post(
        f"{API}/bill-payments/pay",
        headers={**auth_headers(token), "Idempotency-Key": "elec-unified-1"},
        json={
            "category": "electricity",
            "provider_id": "eneo",
            "phone": "1234567890",
            "amount": 100000,
            "pin": "1234",
            "validation_token": token_val,
        },
    )
    assert pay.status_code == 200, pay.text
    status = wait_for_status(client, token, pay.json()["id"])
    assert status == "SUCCESS"
    after = client.get(f"{API}/wallet", headers=auth_headers(token)).json()["balance"]
    assert after == before - 100000


def test_validate_pay_requires_validation_token(client):
    user = register_active_user(client)
    token = user["access_token"]
    _fund(client, token, 300000)
    r = client.post(
        f"{API}/bill-payments/pay",
        headers=auth_headers(token),
        json={
            "category": "electricity",
            "provider_id": "eneo",
            "phone": "1234567890",
            "amount": 100000,
            "pin": "1234",
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] in {"VALIDATION_REQUIRED", "FIELD_REQUIRED", "VALIDATION_NOT_FOUND"}
