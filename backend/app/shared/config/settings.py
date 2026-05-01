from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="EVENTCOMMERCE_",
    )

    app_name: str = "EventCommerce Backend"
    app_version: str = "0.1.0"
    debug: bool = False
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/eventcommerce",
        description="Database connection string for the backend.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
