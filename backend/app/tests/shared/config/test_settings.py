"""Tests for Settings configuration."""

from app.shared.config.settings import Settings


class TestSettings:
    def test_database_url_built_from_atomic_vars(self, monkeypatch):
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_USER", "u")
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_PASSWORD", "p")
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_DB", "db")
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_HOST", "h")
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_PORT", "5433")

        settings = Settings()
        assert settings.database_url == "postgresql+psycopg://u:p@h:5433/db"

    def test_rabbitmq_url_built_from_atomic_vars(self, monkeypatch):
        monkeypatch.setenv("EVENTCOMMERCE_RABBITMQ_USER", "ru")
        monkeypatch.setenv("EVENTCOMMERCE_RABBITMQ_PASSWORD", "rp")
        monkeypatch.setenv("EVENTCOMMERCE_RABBITMQ_HOST", "rh")
        monkeypatch.setenv("EVENTCOMMERCE_RABBITMQ_PORT", "5673")
        monkeypatch.setenv("EVENTCOMMERCE_RABBITMQ_VHOST", "/vhost")

        settings = Settings()
        assert settings.rabbitmq_url == "amqp://ru:rp@rh:5673/vhost"

    def test_test_database_url_builds_from_atomic_vars(self, monkeypatch):
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_USER", "u")
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_PASSWORD", "p")
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_DB", "db")
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_HOST", "h")
        monkeypatch.setenv("EVENTCOMMERCE_POSTGRES_PORT", "5433")

        settings = Settings()
        assert settings.test_database_url == "postgresql+psycopg://u:p@h:5433/db_test"

    def test_app_vars_use_eventcommerce_prefix(self, monkeypatch):
        monkeypatch.setenv("EVENTCOMMERCE_APP_NAME", "TestApp")
        monkeypatch.setenv("EVENTCOMMERCE_DEBUG", "true")

        settings = Settings()
        assert settings.app_name == "TestApp"
        assert settings.debug is True
