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
    resend_api_key: str = ""
    email_from: str = "Banco Magallanes <onboarding@resend.dev>"
    telegram_bot_token: str = ""
    demo_telegram_chat_id: str = ""
    # The phone the first demo customer calls from, in international format. Used by the seed
    # script, so a call from that phone is matched to that customer.
    demo_customer_phone: str = ""
    # The bank's phone line as the app shows it on the sign-in screen. Empty: no line is shown.
    bank_phone_line: str = ""
    app_pin_secret: str = ""
    # True once the contact center has a phone line a call can be transferred to.
    human_line_attached: bool = False
    # The embed snippet of the conversation widget shown in the app, from its provider.
    # `{variables}` in it is replaced by the customer reference, as JSON, `{customer}` by the
    # reference alone, and `{lang}` by the language of the app. Empty: no widget.
    assistant_embed_html: str = ""
    # The CRM that mirrors the insurance sale. Empty instance URL: nothing is mirrored.
    salesforce_instance_url: str = ""
    salesforce_client_id: str = ""
    salesforce_client_secret: str = ""
    salesforce_api_version: str = "v65.0"


@lru_cache
def get_settings() -> Settings:
    """Return the settings, read once and reused. Tests override this dependency."""
    return Settings()
