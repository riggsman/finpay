import time

from app.core.config import settings

from .conftest import auth_headers, register_active_user

API = settings.API_V1_PREFIX

COMPLETE_DRAFT = {
    "first_name": "Kevin",
    "last_name": "Yaounde",
    "date_of_birth": "1990-05-01",
    "address_line": "12 Rue",
    "city": "Yaounde",
    "country": "Cameroon",
    "id_type": "national_id",
    "id_number": "CM123456789",
    "id_document_ref": "id_front.jpg",
    "id_document_back_ref": "id_back.jpg",
    "selfie_ref": "selfie.jpg",
}


def _wait_status(client, token, targets, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = client.get(f"{API}/me/kyc", headers=auth_headers(token)).json()["status"]
        if s in targets:
            return s
        time.sleep(0.1)
    raise AssertionError(f"KYC did not reach {targets}")


def test_initial_status_not_started(client):
    user = register_active_user(client)
    r = client.get(f"{API}/me/kyc", headers=auth_headers(user["access_token"]))
    assert r.status_code == 200
    assert r.json()["status"] == "NOT_STARTED"


def test_submit_incomplete_rejected(client):
    user = register_active_user(client)
    r = client.post(f"{API}/me/kyc/submit", headers=auth_headers(user["access_token"]))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "KYC_INCOMPLETE"


def test_draft_sets_in_progress(client):
    user = register_active_user(client)
    r = client.put(
        f"{API}/me/kyc", headers=auth_headers(user["access_token"]), json=COMPLETE_DRAFT
    )
    assert r.status_code == 200
    assert r.json()["status"] == "IN_PROGRESS"


def test_kyc_approval_does_not_raise_limits(client):
    user = register_active_user(client)
    token = user["access_token"]

    before = client.get(f"{API}/me/security/limits", headers=auth_headers(token)).json()
    assert before["per_txn_limit"] == settings.DEFAULT_PER_TXN_LIMIT

    client.put(f"{API}/me/kyc", headers=auth_headers(token), json=COMPLETE_DRAFT)
    submit = client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))
    assert submit.json()["status"] == "UNDER_REVIEW"

    assert _wait_status(client, token, {"APPROVED"}) == "APPROVED"

    after = client.get(f"{API}/me/security/limits", headers=auth_headers(token)).json()
    assert after["per_txn_limit"] == settings.DEFAULT_PER_TXN_LIMIT
    assert after["daily_limit"] == settings.DEFAULT_DAILY_LIMIT

    notifs = client.get(f"{API}/notifications", headers=auth_headers(token)).json()
    approved = next(n for n in notifs if n["type"] == "KYC_APPROVED")
    assert "Successful KYC verification" in approved["title"]
    assert "limit" not in approved["message"].lower()


def test_kyc_rejection_for_bad_id(client):
    user = register_active_user(client)
    token = user["access_token"]
    draft = {**COMPLETE_DRAFT, "id_number": "CM000000000"}  # ends in 0000 -> rejected
    client.put(f"{API}/me/kyc", headers=auth_headers(token), json=draft)
    client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))

    assert _wait_status(client, token, {"REJECTED"}) == "REJECTED"
    kyc = client.get(f"{API}/me/kyc", headers=auth_headers(token)).json()
    assert kyc["rejection_reason"]

    notifs = client.get(f"{API}/notifications", headers=auth_headers(token)).json()
    assert any(n["type"] == "KYC_REJECTED" for n in notifs)


def test_kyc_camera_capture_persists_front_back_selfie(client, tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "KYC_UPLOAD_DIR", str(tmp_path))
    user = register_active_user(client)
    token = user["access_token"]
    # Long synthetic payload so size validation passes.
    payload = "data:image/jpeg;base64," + ("A" * 400)

    front = client.post(
        f"{API}/me/kyc/capture",
        headers=auth_headers(token),
        json={"kind": "front", "image_base64": payload},
    )
    assert front.status_code == 200
    assert front.json()["field"] == "id_document_ref"

    back = client.post(
        f"{API}/me/kyc/capture",
        headers=auth_headers(token),
        json={"kind": "back", "image_base64": payload},
    )
    assert back.status_code == 200
    assert back.json()["field"] == "id_document_back_ref"

    selfie = client.post(
        f"{API}/me/kyc/capture",
        headers=auth_headers(token),
        json={"kind": "selfie", "image_base64": payload},
    )
    assert selfie.status_code == 200

    kyc = client.get(f"{API}/me/kyc", headers=auth_headers(token)).json()
    assert kyc["id_document_ref"]
    assert kyc["id_document_back_ref"]
    assert kyc["selfie_ref"]

    media = client.get(
        f"{API}/me/kyc/media/{kyc['id_document_ref']}",
        headers=auth_headers(token),
    )
    assert media.status_code == 200


def test_kyc_decision_sends_email(client):
    from app.notifications import email as email_channel

    email_channel.sent_log.clear()
    user = register_active_user(client)
    token = user["access_token"]
    client.put(f"{API}/me/kyc", headers=auth_headers(token), json=COMPLETE_DRAFT)
    client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))
    assert _wait_status(client, token, {"APPROVED"}) == "APPROVED"

    deadline = time.time() + 3
    while time.time() < deadline and not any(
        "Identity verified" in (m.get("subject") or "") for m in email_channel.sent_log
    ):
        time.sleep(0.05)
    assert any("Identity verified" in (m.get("subject") or "") for m in email_channel.sent_log)


def test_cannot_submit_twice(client):
    user = register_active_user(client)
    token = user["access_token"]
    client.put(f"{API}/me/kyc", headers=auth_headers(token), json=COMPLETE_DRAFT)
    client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))
    # Immediately try again while under review.
    again = client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "KYC_ALREADY_SUBMITTED"


def test_admin_can_reject_approved_but_not_approve_rejected(client, admin_token):
    user = register_active_user(client)
    token = user["access_token"]
    client.put(f"{API}/me/kyc", headers=auth_headers(token), json=COMPLETE_DRAFT)
    client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))
    assert _wait_status(client, token, {"APPROVED"}) == "APPROVED"

    kyc = client.get(f"{API}/me/kyc", headers=auth_headers(token)).json()
    # Find KYC id via admin list
    rows = client.get(
        f"{API}/admin/kyc",
        headers=auth_headers(admin_token),
        params={"user_id": user["user"]["id"]},
    ).json()
    assert rows
    kyc_id = rows[0]["id"]

    rejected = client.post(
        f"{API}/admin/kyc/{kyc_id}/reject",
        headers=auth_headers(admin_token),
        json={"reason": "Document mismatch after approval"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    limits = client.get(f"{API}/me/security/limits", headers=auth_headers(token)).json()
    assert limits["per_txn_limit"] == settings.DEFAULT_PER_TXN_LIMIT

    blocked = client.post(
        f"{API}/admin/kyc/{kyc_id}/approve",
        headers=auth_headers(admin_token),
        json={},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "KYC_CANNOT_APPROVE_REJECTED"

