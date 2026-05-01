"""Notifications API schemas."""

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    notification_id: str
    order_id: str
    channel: str
    content: str
