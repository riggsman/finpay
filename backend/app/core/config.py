from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "FinPay"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "mysql+pymysql://root@localhost:3306/finpay"
    # DATABASE_URL: str = "postgresql+psycopg2://finpay:finpay@localhost:5432/finpay"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = "change-me-in-production-please-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 900
    REFRESH_TOKEN_EXPIRE_SECONDS: int = 1209600

    OTP_TTL_SECONDS: int = 300
    OTP_MAX_ATTEMPTS: int = 5
    EXPOSE_OTP_IN_RESPONSE: bool = True

    # Password reset lifetimes.
    RESET_CODE_TTL_SECONDS: int = 300
    RESET_TOKEN_TTL_SECONDS: int = 600

    # Default transaction limits (minor units) — 500,000.00 XAF each.
    DEFAULT_PER_TXN_LIMIT: int = 50_000_000  # 500,000.00
    DEFAULT_DAILY_LIMIT: int = 50_000_000  # 500,000.00

    # Legacy env fallbacks (limit raises are admin-approved requests, not KYC).
    KYC_APPROVED_PER_TXN_LIMIT: int = 200_000_000  # 2,000,000.00
    KYC_APPROVED_DAILY_LIMIT: int = 1_000_000_000  # 10,000,000.00
    # Simulated KYC review delay (seconds). Set KYC_AUTO_REVIEW_ENABLED=false
    # so Back Office admins validate submissions manually.
    KYC_REVIEW_DELAY_SECONDS: float = 2.0
    KYC_AUTO_REVIEW_ENABLED: bool = False
    KYC_UPLOAD_DIR: str = "uploads/kyc"
    SUPPORT_UPLOAD_DIR: str = "uploads/support"

    # Default transaction PIN assigned at activation (development convenience).
    DEFAULT_TRANSACTION_PIN: str = "1234"

    # Back Office bootstrap admin (seeded on startup for development).
    ADMIN_EMAIL: str = "admin@local.dev"
    ADMIN_PHONE: str = "+237600000001"
    ADMIN_PASSWORD: str = "admin1234"

    # Shared mailbox domain for all FinPay users (dev/test notifications).
    # New accounts get emails like john@local.dev.
    USER_EMAIL_DOMAIN: str = "local.dev"
    # Validation token lifetime for bill payments (seconds).
    VALIDATION_TOKEN_TTL_SECONDS: int = 300
    # Simulated provider processing delay (seconds) for the electricity flow.
    PROVIDER_PROCESSING_DELAY_SECONDS: float = 2.0

    # Reconciliation worker: settles transactions left pending by provider timeouts.
    RECONCILE_WORKER_ENABLED: bool = True
    RECONCILE_INTERVAL_SECONDS: float = 3.0
    RECONCILE_MIN_AGE_SECONDS: float = 1.0

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Rate limiting (Redis-backed; fails open if Redis is unavailable) ---
    RATE_LIMIT_ENABLED: bool = True
    RL_OTP_INITIATE_LIMIT: int = 6
    RL_OTP_INITIATE_WINDOW: int = 600
    RL_LOGIN_LIMIT: int = 10
    RL_LOGIN_WINDOW: int = 300
    RL_PASSWORD_RESET_LIMIT: int = 5
    RL_PASSWORD_RESET_WINDOW: int = 600
    RL_VERIFY_OTP_LIMIT: int = 12
    RL_VERIFY_OTP_WINDOW: int = 600
    # Per-connection Socket.IO event rate limit.
    SOCKET_EVENT_LIMIT: int = 30
    SOCKET_EVENT_WINDOW: float = 10.0

    # --- Firebase Cloud Messaging (push) ---
    # Provide EITHER the full service-account JSON in FCM_SERVICE_ACCOUNT_JSON,
    # OR the three individual fields below, OR set GOOGLE_APPLICATION_CREDENTIALS
    # to a service-account file path. Leave all empty to disable FCM (the app
    # still runs and delivers via Socket.IO only).
    FCM_SERVICE_ACCOUNT_JSON: str = ""
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CLIENT_EMAIL: str = ""
    FIREBASE_PRIVATE_KEY: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    # Also send FCM (in addition to Socket.IO) for these priorities even when the
    # user is connected. Otherwise FCM is only used when the user is offline.
    FCM_ALWAYS_PRIORITIES: str = "CRITICAL"

    # --- Email notifications ---
    # EMAIL_BACKEND: console (logs emails, default), smtp, or disabled.
    # In development the embedded mail catcher starts with the API and routes
    # console/local smtp traffic to it automatically.
    EMAIL_BACKEND: str = "console"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: str = "no-reply@finpay.app"

    # Embedded local mail catcher (no Docker). Auto-started with the backend
    # when ENVIRONMENT is development/dev/local.
    DEV_MAIL_SERVER_ENABLED: bool = True
    DEV_MAIL_SMTP_HOST: str = "127.0.0.1"
    DEV_MAIL_SMTP_PORT: int = 1025
    DEV_MAIL_WEB_HOST: str = "127.0.0.1"
    DEV_MAIL_WEB_PORT: int = 1080

    # --- Campay (mobile money collection / withdrawal) ---
    # Secrets must come from environment / .env — never commit real values.
    # Credentials alone enable the Back Office Campay sandbox. Wallet MoMo
    # collect/withdraw still require PAYMENT_MODE=live (see campay_configured()).
    CAMPAY_USERNAME: str = ""
    CAMPAY_PASSWORD: str = ""
    CAMPAY_BASE_URL: str = "https://demo.campay.net"
    CAMPAY_WEBHOOK_KEY: str = ""
    CAMPAY_TIMEOUT_SECONDS: float = 30.0

    # Payment mode switch: "simulated" keeps wallet deposits/withdrawals on the
    # local mock path (safe for demos). "live" routes MoMo through Campay when
    # credentials are present. Admin sandbox can call Campay in either mode.
    PAYMENT_MODE: str = "simulated"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def use_redis(self) -> bool:
        return bool(self.REDIS_URL)

    @property
    def fcm_always_priorities(self) -> set[str]:
        return {p.strip().upper() for p in self.FCM_ALWAYS_PRIORITIES.split(",") if p.strip()}

    @property
    def fcm_configured(self) -> bool:
        return bool(
            self.FCM_SERVICE_ACCOUNT_JSON
            or self.GOOGLE_APPLICATION_CREDENTIALS
            or (self.FIREBASE_PROJECT_ID and self.FIREBASE_CLIENT_EMAIL and self.FIREBASE_PRIVATE_KEY)
        )

    @property
    def campay_configured(self) -> bool:
        return bool((self.CAMPAY_USERNAME or "").strip() and (self.CAMPAY_PASSWORD or "").strip())

    @property
    def payment_mode(self) -> str:
        return (self.PAYMENT_MODE or "simulated").strip().lower()

    @property
    def payments_live(self) -> bool:
        return self.payment_mode == "live"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
