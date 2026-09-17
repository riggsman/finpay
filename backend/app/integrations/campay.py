"""Campay mobile-money HTTP client.

Credentials come from settings (CAMPAY_USERNAME / CAMPAY_PASSWORD). When they
are unset the wallet layer keeps the local mock path.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger("finpay.campay")

_PHONE_DIGITS = re.compile(r"\D+")


class CampayError(AppError):
    """Campay API / transport failure (upstream provider error).

    NOT a request-validation failure: inherit from ``AppError`` (400) but
    surface as 502 Bad Gateway so clients can tell the difference between
    a bad request and an unavailable/declining provider.
    """

    status_code = 502  # BAD_GATEWAY
    code = "CAMPAY_ERROR"


def campay_credentials_ready() -> bool:
    """True when CAMPAY_USERNAME / CAMPAY_PASSWORD are set (sandbox or live)."""
    return bool(settings.campay_configured)


def campay_configured() -> bool:
    """Wallet MoMo may call Campay only when live mode AND credentials exist.

    Simulated mode keeps deposit/withdraw on the local mock path so demos and
    CI never move real money. Admin sandbox uses ``campay_credentials_ready``
    instead so operators can still probe Campay without flipping live mode.
    """
    return settings.payments_live and campay_credentials_ready()


def normalize_msisdn(phone: str | None) -> str:
    """Normalize to Campay form ``2376xxxxxxxx`` (digits only, country code)."""
    raw = (phone or "").strip()
    if not raw:
        raise CampayError("Phone number is required.", code="INVALID_PHONE")
    digits = _PHONE_DIGITS.sub("", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("237"):
        pass
    elif len(digits) == 9 and digits.startswith("6"):
        digits = "237" + digits
    elif len(digits) == 10 and digits.startswith("06"):
        digits = "237" + digits[1:]
    else:
        raise CampayError(
            "Invalid phone number. Use a Cameroon MTN/Orange number with country code.",
            code="INVALID_PHONE",
        )
    if len(digits) != 12 or not digits.startswith("237"):
        raise CampayError(
            "Invalid phone number. Expected 237 followed by 9 digits.",
            code="INVALID_PHONE",
        )
    return digits


def minor_to_campay_amount(amount_minor: int) -> int:
    """Convert FinPay minor units to Campay whole XAF. Reject fractional francs."""
    if amount_minor is None or int(amount_minor) <= 0:
        raise CampayError("Amount must be positive.", code="INVALID_AMOUNT")
    amount_minor = int(amount_minor)
    if amount_minor % 100 != 0:
        raise CampayError(
            "Amount must be a whole number of XAF (no centimes).",
            code="INVALID_AMOUNT",
        )
    return amount_minor // 100


def is_campay_reference(ref: str | None) -> bool:
    """Heuristic: Campay transaction references are UUID4 strings."""
    if not ref:
        return False
    text = str(ref).strip()
    return bool(
        re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            text,
        )
    )


def map_campay_status(status: str | None) -> str:
    """Normalize Campay status to SUCCESS | FAILED | PENDING."""
    s = (status or "").strip().upper()
    if s in ("SUCCESSFUL", "SUCCESS", "SUCCESSFULLY"):
        return "SUCCESS"
    if s in ("FAILED", "FAILURE", "ERROR"):
        return "FAILED"
    return "PENDING"


class CampayClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def base_url(self) -> str:
        return (settings.CAMPAY_BASE_URL or "https://demo.campay.net").rstrip("/")

    def _require_configured(self) -> None:
        # HTTP calls need credentials only; PAYMENT_MODE gates wallet usage
        # separately via campay_configured().
        if not campay_credentials_ready():
            raise CampayError(
                "Campay is not configured. Set CAMPAY_USERNAME and CAMPAY_PASSWORD.",
                code="CAMPAY_NOT_CONFIGURED",
            )

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=float(settings.CAMPAY_TIMEOUT_SECONDS or 30),
        )

    def _raise_from_response(self, response: httpx.Response) -> None:
        try:
            data = response.json()
        except Exception:
            data = {"detail": response.text}
        message = None
        code = "CAMPAY_ERROR"
        if isinstance(data, dict):
            message = (
                data.get("message")
                or data.get("detail")
                or data.get("error")
                or data.get("msg")
            )
            err = data.get("error") or data.get("code")
            if isinstance(err, str) and err.startswith("ER"):
                code = err
                message = message or err
            if isinstance(data.get("message"), dict):
                message = str(data["message"])
        if not message:
            message = f"Campay request failed ({response.status_code})."
        if code == "ER101":
            code = "INVALID_PHONE"
            message = "Invalid phone number for Campay."
        elif code == "ER102":
            code = "UNSUPPORTED_CARRIER"
            message = "Unsupported carrier. Use MTN or Orange Cameroon."
        elif code == "ER201":
            code = "INVALID_AMOUNT"
            message = "Invalid amount for Campay."
        elif code == "ER301":
            code = "INSUFFICIENT_PROVIDER_BALANCE"
            message = "Insufficient Campay merchant balance for this carrier."
        raise CampayError(str(message), code=code)

    def get_token(self, *, force: bool = False) -> str:
        self._require_configured()
        with self._lock:
            if (
                not force
                and self._token
                and time.time() < self._token_expires_at - 30
            ):
                return self._token
            with self._client() as client:
                response = client.post(
                    "/api/token/",
                    json={
                        "username": settings.CAMPAY_USERNAME.strip(),
                        "password": settings.CAMPAY_PASSWORD.strip(),
                    },
                )
            if response.status_code >= 400:
                self._raise_from_response(response)
            data = response.json()
            token = data.get("token") or data.get("access_token")
            if not token:
                raise CampayError("Campay token response missing token.", code="CAMPAY_ERROR")
            expires_in = int(data.get("expires_in") or 3600)
            self._token = str(token)
            self._token_expires_at = time.time() + max(60, expires_in)
            return self._token

    def _auth_headers(self, *, force_token: bool = False) -> dict[str, str]:
        token = self.get_token(force=force_token)
        return {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        self._require_configured()
        headers = self._auth_headers()
        with self._client() as client:
            response = client.request(
                method, path, json=json, params=params, headers=headers
            )
        if response.status_code in (401, 403) and retry_auth:
            headers = self._auth_headers(force_token=True)
            with self._client() as client:
                response = client.request(
                    method, path, json=json, params=params, headers=headers
                )
        if response.status_code >= 400:
            self._raise_from_response(response)
        if not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}

    def collect(
        self,
        *,
        amount_xaf: int,
        phone: str,
        description: str,
        external_reference: str,
    ) -> dict[str, Any]:
        msisdn = normalize_msisdn(phone)
        payload = {
            "amount": str(int(amount_xaf)),
            "currency": "XAF",
            "from": msisdn,
            "description": (description or "FinPay deposit")[:255],
            "external_reference": external_reference,
        }
        logger.info(
            "Campay collect amount=%s from=%s ref=%s",
            amount_xaf,
            msisdn,
            external_reference,
        )
        return self._request("POST", "/api/collect/", json=payload)

    def withdraw(
        self,
        *,
        amount_xaf: int,
        phone: str,
        description: str,
        external_reference: str,
    ) -> dict[str, Any]:
        msisdn = normalize_msisdn(phone)
        payload = {
            "amount": str(int(amount_xaf)),
            "currency": "XAF",
            "to": msisdn,
            "description": (description or "FinPay withdrawal")[:255],
            "external_reference": external_reference,
        }
        logger.info(
            "Campay withdraw amount=%s to=%s ref=%s",
            amount_xaf,
            msisdn,
            external_reference,
        )
        return self._request("POST", "/api/withdraw/", json=payload)

    def get_transaction(self, reference: str) -> dict[str, Any]:
        ref = (reference or "").strip()
        if not ref:
            raise CampayError("Campay reference is required.", code="INVALID_REFERENCE")
        return self._request("GET", f"/api/transaction/{ref}/")

    def get_balance(self) -> dict[str, Any]:
        return self._request("GET", "/api/balance/")

    def holder_info(self, phone: str) -> dict[str, Any]:
        msisdn = normalize_msisdn(phone)
        return self._request(
            "GET",
            "/api/holder_info/",
            params={"phone_number": msisdn},
        )


_client: CampayClient | None = None
_client_lock = threading.Lock()


def get_campay_client() -> CampayClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = CampayClient()
        return _client


def reset_campay_client() -> None:
    """Test helper to clear cached client/token."""
    global _client
    with _client_lock:
        _client = None
