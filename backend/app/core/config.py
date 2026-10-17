from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8')

    MONGO_URI: str
    MONGO_DB_NAME: str

    REDIS_URL: str
    
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    WHATSAPP_API_VERSION: str
    WHATSAPP_ACCESS_TOKEN: str  
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_VERIFY_TOKEN: str 
    WHATSAPP_APPROVED_TEMPLATE_NAME: str = ""
    # Approved template names per reminder purpose. A template name is accepted
    # by the sender only when it appears in one of these settings (or in
    # WHATSAPP_APPROVED_TEMPLATE_NAME). Leave blank until Meta approves them.
    WHATSAPP_MEDICATION_TEMPLATE_NAME: str = ""
    WHATSAPP_REFILL_TEMPLATE_NAME: str = ""
    WHATSAPP_TEMPLATE_LANGUAGE: str = "en_US"
    # Meta app secret used to verify inbound webhook signatures. Optional; when
    # blank, inbound delivery callbacks are accepted without signature checks.
    WHATSAPP_APP_SECRET: str = ""

    # Telegram Bot API configuration for reminder delivery. The token is read
    # only from the backend environment and is never exposed to the frontend
    # (no EXPO_PUBLIC_ variables) or written to logs. Leaving it blank keeps
    # Telegram delivery disabled.
    TELEGRAM_BOT_TOKEN: str = ""
    # Bot username without the leading "@", used to build a t.me deep link that
    # carries the one-time account-linking code. Optional.
    TELEGRAM_BOT_USERNAME: str = ""
    # Secret token configured through Telegram's setWebhook call. When set,
    # inbound webhook requests must present it in the
    # X-Telegram-Bot-Api-Secret-Token header.
    TELEGRAM_WEBHOOK_SECRET: str = ""
    # Lifetime of a one-time Telegram account-linking code, in seconds.
    TELEGRAM_LINK_CODE_TTL_SECONDS: int = 900

    # Geoapify Places API key used by pharmacy lookup. Optional; when blank the
    # pharmacy search endpoint reports a clear "not configured" state.
    GEOAPIFY_API_KEY: str = ""

    GCP_PROJECT_ID: str
    GCP_LOCATION: str
    GOOGLE_APPLICATION_CREDENTIALS: str

    # Gemini Developer API (Google AI Studio) configuration. The key is read
    # exclusively from the backend environment and must never be exposed to the
    # frontend (no EXPO_PUBLIC_ variables) or printed to logs.
    GEMINI_API_KEY: str = ""
    # Optional model override. Leave blank to use the service default
    # (gemini-3.5-flash-lite, free-tier supported and low latency).
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # Report interpretation mode: "local" keeps extraction credential-free,
    # "ai" enables Gemini report analysis when GEMINI_API_KEY is configured.
    REPORT_ANALYSIS_MODE: str = "local"

settings = Settings()
