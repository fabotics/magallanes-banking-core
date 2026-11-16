"""Settings read from environment variables.

Every value the app needs from outside lives here, so no other module reads
the environment directly. Locally the values come from a `.env` file that is
never committed. In production they come from the hosting dashboard.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view of the environment. Empty defaults let the app start without a `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_secret_key: str = ""
    bank_api_key: str = ""
    public_base_url: str = "http://localhost:8000"
    demo_customer_email: str = ""
    transactions_delay_seconds: float = 1.0


@lru_cache
def get_settings() -> Settings:
    """Return the settings, read once and reused. Tests override this dependency."""
    return Settings()
