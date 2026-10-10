import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "PayLedger API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DESCRIPTION: str = (
        "Production-grade Double-Entry Payment Ledger API with balanced journal accounting, "
        "concurrency-safe idempotency keys, JWT OAuth2 authentication, role-based access control, "
        "rate limiting, background reconciliation, and comprehensive mutation audit logging."
    )

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./payledger.db")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "payledger-super-secure-secret-key-change-in-production-2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Rate Limiting
    TRANSFER_RATE_LIMIT: str = "30/minute"

    # Worker / Scheduler
    ENABLE_SCHEDULER: bool = os.getenv("ENABLE_SCHEDULER", "true").lower() in ("true", "1", "yes")
    RECONCILIATION_INTERVAL_SECONDS: int = int(os.getenv("RECONCILIATION_INTERVAL_SECONDS", "60"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
