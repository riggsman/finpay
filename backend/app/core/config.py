from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "FinPay"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+psycopg2://finpay:finpay@localhost:5432/finpay"
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

    # Default transaction limits (minor units).
    DEFAULT_PER_TXN_LIMIT: int = 50_000_000  # 500,000.00
    DEFAULT_DAILY_LIMIT: int = 200_000_000  # 2,000,000.00

    # Higher limits granted once KYC is approved.
    KYC_APPROVED_PER_TXN_LIMIT: int = 200_000_000  # 2,000,000.00
    KYC_APPROVED_DAILY_LIMIT: int = 1_000_000_000  # 10,000,000.00
    # Simulated KYC review delay (seconds).
    KYC_REVIEW_DELAY_SECONDS: float = 2.0

    # Default transaction PIN assigned at activation (development convenience).
    DEFAULT_TRANSACTION_PIN: str = "1234"
    # Validation token lifetime for bill payments (seconds).
    VALIDATION_TOKEN_TTL_SECONDS: int = 300
    # Simulated provider processing delay (seconds) for the electricity flow.
    PROVIDER_PROCESSING_DELAY_SECONDS: float = 2.0

    # Reconciliation worker: settles transactions left pending by provider timeouts.
    RECONCILE_WORKER_ENABLED: bool = True
    RECONCILE_INTERVAL_SECONDS: float = 5.0
    RECONCILE_MIN_AGE_SECONDS: float = 3.0

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def use_redis(self) -> bool:
        return bool(self.REDIS_URL)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
