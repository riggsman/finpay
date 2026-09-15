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


def test_kyc_approval_raises_limits(client):
    user = register_active_user(client)
    token = user["access_token"]

    before = client.get(f"{API}/me/security/limits", headers=auth_headers(token)).json()
    assert before["per_txn_limit"] == settings.DEFAULT_PER_TXN_LIMIT

    client.put(f"{API}/me/kyc", headers=auth_headers(token), json=COMPLETE_DRAFT)
    submit = client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))
    assert submit.json()["status"] == "UNDER_REVIEW"

    assert _wait_status(client, token, {"APPROVED"}) == "APPROVED"

    after = client.get(f"{API}/me/security/limits", headers=auth_headers(token)).json()
    assert after["per_txn_limit"] == settings.KYC_APPROVED_PER_TXN_LIMIT
    assert after["daily_limit"] == settings.KYC_APPROVED_DAILY_LIMIT

    notifs = client.get(f"{API}/notifications", headers=auth_headers(token)).json()
    assert any(n["type"] == "KYC_APPROVED" for n in notifs)


def test_kyc_rejection_for_bad_id(client):
    user = register_active_user(client)
    token = user["access_token"]
    draft = {**COMPLETE_DRAFT, "id_number": "CM000000000"}  # ends in 0000 -> rejected
    client.put(f"{API}/me/kyc", headers=auth_headers(token), json=draft)
    client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))

    assert _wait_status(client, token, {"REJECTED"}) == "REJECTED"
    kyc = client.get(f"{API}/me/kyc", headers=auth_headers(token)).json()
    assert kyc["rejection_reason"]


def test_cannot_submit_twice(client):
    user = register_active_user(client)
    token = user["access_token"]
    client.put(f"{API}/me/kyc", headers=auth_headers(token), json=COMPLETE_DRAFT)
    client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))
    # Immediately try again while under review.
    again = client.post(f"{API}/me/kyc/submit", headers=auth_headers(token))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "KYC_ALREADY_SUBMITTED"
