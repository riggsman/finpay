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


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


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
