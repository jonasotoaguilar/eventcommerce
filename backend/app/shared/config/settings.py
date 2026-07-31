from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="EVENTCOMMERCE_",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "EventCommerce Backend"
    app_version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    postgres_user: str = Field(default="postgres", alias="EVENTCOMMERCE_POSTGRES_USER")
    postgres_password: str = Field(
        default="postgres", alias="EVENTCOMMERCE_POSTGRES_PASSWORD"
    )
    postgres_db: str = Field(default="eventcommerce", alias="EVENTCOMMERCE_POSTGRES_DB")
    postgres_host: str = Field(default="localhost", alias="EVENTCOMMERCE_POSTGRES_HOST")
    postgres_port: str = Field(default="5432", alias="EVENTCOMMERCE_POSTGRES_PORT")

    rabbitmq_user: str = Field(default="guest", alias="EVENTCOMMERCE_RABBITMQ_USER")
    rabbitmq_password: str = Field(
        default="guest", alias="EVENTCOMMERCE_RABBITMQ_PASSWORD"
    )
    rabbitmq_host: str = Field(default="localhost", alias="EVENTCOMMERCE_RABBITMQ_HOST")
    rabbitmq_port: str = Field(default="5672", alias="EVENTCOMMERCE_RABBITMQ_PORT")
    rabbitmq_vhost: str = Field(default="/", alias="EVENTCOMMERCE_RABBITMQ_VHOST")

    @computed_field
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    def test_database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}_test"
        )

    @computed_field
    def rabbitmq_url(self) -> str:
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}{self.rabbitmq_vhost}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
