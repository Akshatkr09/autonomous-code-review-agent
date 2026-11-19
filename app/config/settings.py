"""Centralized, typed application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration loaded from environment variables and an optional .env file."""

    app_env: str = "development"
    log_level: str = "INFO"
    github_token: str = Field(default="", repr=False)
    openai_api_key: str = Field(default="", repr=False)
    github_webhook_secret: str = Field(default="", repr=False)
    openai_model: str = "gpt-4o-mini"
    database_path: str = "./data/review_checkpoints.sqlite"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_file(self) -> Path:
        """Return the configured checkpoint database path."""
        return Path(self.database_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
