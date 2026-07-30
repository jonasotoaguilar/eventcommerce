"""Tests for notification domain services."""

from app.modules.notifications.domain.services import is_channel_supported


class TestIsChannelSupported:
    def test_email_supported(self) -> None:
        assert is_channel_supported("email") is True

    def test_sms_supported(self) -> None:
        assert is_channel_supported("sms") is True

    def test_push_supported(self) -> None:
        assert is_channel_supported("push") is True

    def test_unknown_channel_not_supported(self) -> None:
        assert is_channel_supported("fax") is False
        assert is_channel_supported("") is False
