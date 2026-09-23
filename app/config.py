from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_score_model: str = "gemini-flash-lite-latest"
    gemini_research_model: str = "gemini-flash-latest"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""         # full access. one id, or several separated by commas
    telegram_metals_chat_id: str = ""  # gold and silver alerts only, nothing else
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

    @staticmethod
    def _ids(raw: str) -> list[str]:
        return [part.strip() for part in str(raw or "").split(",") if part.strip()]

    @property
    def chat_ids(self) -> list[str]:
        """Full access: every command, every alert. This is who the bot is for."""
        return self._ids(self.telegram_chat_id)

    @property
    def metals_chat_ids(self) -> list[str]:
        """Gold and silver level alerts only. Nothing else in the bot answers them."""
        return [c for c in self._ids(self.telegram_metals_chat_id) if c not in self.chat_ids]

    @property
    def level_chat_ids(self) -> list[str]:
        """Everyone who gets metal levels: you, and anyone you shared them with."""
        return self.chat_ids + self.metals_chat_ids

    def may_use(self, chat_id) -> bool:
        return str(chat_id) in self.chat_ids

    def may_see_metals(self, chat_id) -> bool:
        return str(chat_id) in self.level_chat_ids


settings = Settings()
