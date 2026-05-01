"""Notification channel value object."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationChannel:
    name: str
