from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_score_model: str = "gemini-flash-lite-latest"
    gemini_research_model: str = "gemini-flash-latest"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite:///data/radar.db"
    urgent_daily_cap: int = 3
    digest_total: int = 6
    digest_per_topic: int = 2
    research_daily_cap: int = 40
    coingecko_api_key: str = ""       # free "demo" key from coingecko.com (recommended)
    fetch_interval_min: int = 45
    scout_interval_min: int = 120
    digest_hour: int = 9
    timezone: str = "Asia/Kolkata"


settings = Settings()
