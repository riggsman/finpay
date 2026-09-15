import random
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

API = settings.API_V1_PREFIX


@pytest.fixture(scope="session", autouse=True)
def _fast_provider():
    # Speed up simulated async operations so completion tests are quick.
    settings.PROVIDER_PROCESSING_DELAY_SECONDS = 0.1
    settings.KYC_REVIEW_DELAY_SECONDS = 0.1
    # Reconcile deterministically via the manual endpoint; no background worker.
    settings.RECONCILE_WORKER_ENABLED = False
    settings.RECONCILE_MIN_AGE_SECONDS = 0
    yield


@pytest.fixture(autouse=True)
def _reset_fees_and_services():
    """Reset fee rules to zero and enable all services before each test so the
    fee configuration (which persists in the shared DB) never leaks between
    tests."""
    import json

    from app.db.database import SessionLocal
    from app.models.fees import FeeRule, ServiceFlag
    from app.services import fee_service

    db = SessionLocal()
    try:
        fee_service.seed_defaults(db)
        db.query(FeeRule).update(
            {FeeRule.fee_type: "FLAT", FeeRule.config: json.dumps({"fee": 0}),
             FeeRule.active: True}
        )
        db.query(ServiceFlag).update({ServiceFlag.enabled: True})
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token():
    """Log in the seeded Back Office admin once for the whole session."""
    with TestClient(app) as c:
        r = c.post(
            f"{API}/auth/login",
            json={"identifier": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD},
        )
        return r.json()["access_token"]


def unique_phone() -> str:
    return "+2376" + "".join(random.choices("0123456789", k=8))


def register_active_user(client: TestClient, password: str = "Password123") -> dict:
    """Create a fully activated user and return tokens + identity."""
    phone = unique_phone()
    client.post(f"{API}/auth/register/initiate", json={"phone": phone})
    client.post(
        f"{API}/auth/register",
        json={
            "signup_method": "phone",
            "phone": phone,
            "first_name": "Test",
            "last_name": "User",
            "email": f"{phone.strip('+')}@example.com",
            "password": password,
        },
    )
    otp = client.post(
        f"{API}/auth/register/initiate", json={"phone": phone}
    ).json()["otp_debug"]
    res = client.post(f"{API}/auth/verify-otp", json={"phone": phone, "otp": otp}).json()
    return {"phone": phone, "password": password, **res}


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def wait_for_status(client: TestClient, token: str, txn_id: int,
                    targets=("SUCCESS", "FAILED"), timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"{API}/transactions/{txn_id}", headers=auth_headers(token))
        status = r.json()["status"]
        if status in targets:
            return status
        time.sleep(0.1)
    raise AssertionError(f"transaction {txn_id} did not reach {targets} in time")
