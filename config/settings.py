from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = ""

    # Telegram
    telegram_bot_token: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_app_token: str = ""

    # Database
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'secretary.db'}"

    # Defaults
    default_family_name: str = "우리가족"
    default_timezone: str = "Asia/Seoul"

    # Claude model
    claude_model: str = "claude-sonnet-4-5"

    # Web search (optional)
    brave_search_api_key: str = ""


settings = Settings()
