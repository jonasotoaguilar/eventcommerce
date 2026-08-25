"""ProcessOrderNotification use case — idempotent terminal-event notifier."""

from uuid import UUID

from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.shared.messaging.idempotency import ProcessedEventStore

CONSUMER_NAME = "ProcessOrderNotification"
NOTIFICATION_CHANNEL = "email"


class ProcessOrderNotification:
    def __init__(
        self, notifier: SendOrderNotification, idempotency: ProcessedEventStore
    ) -> None:
        self._notifier = notifier
        self._idempotency = idempotency

    async def execute(
        self,
        *,
        payload: dict,
        event_id: str,
        event_type: str,
        aggregate_id: str,
    ) -> None:
        if await self._idempotency.is_processed(event_id, CONSUMER_NAME):
            return
        order_id = UUID(str(aggregate_id))
        if event_type == "OrderConfirmed":
            content = "Your order has been confirmed"
        elif event_type == "OrderCancelled":
            content = "Your order could not be completed"
        else:
            raise ValueError(f"unsupported event_type: {event_type}")
        await self._notifier.execute(
            order_id=order_id, channel=NOTIFICATION_CHANNEL, content=content
        )
        await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
