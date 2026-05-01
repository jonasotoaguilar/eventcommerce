"""Notifications domain errors."""

class NotificationsDomainError(Exception):
    """Base error for notifications domain."""


class ChannelNotSupportedError(NotificationsDomainError):
    """Raised when the notification channel is not supported."""

