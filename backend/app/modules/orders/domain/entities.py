"""Order domain entities."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from app.modules.orders.domain.errors import InvalidStateTransitionError
from app.modules.orders.domain.services import can_transition


@dataclass(frozen=True)
class OrderItem:
    product_id: str
    quantity: int


@dataclass
class Order:
    id: UUID
    customer_id: str
    status: str
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItem] = field(default_factory=list)

    def confirm(self) -> None:
        if not can_transition(self.status, "confirmed"):
            raise InvalidStateTransitionError(
                f"Cannot confirm order from status {self.status}"
            )
        if self.status != "confirmed":
            self.status = "confirmed"
            self.updated_at = datetime.now(timezone.utc)

    def cancel(self, reason: str) -> None:
        if not can_transition(self.status, "cancelled"):
            raise InvalidStateTransitionError(
                f"Cannot cancel order from status {self.status}"
            )
        if self.status != "cancelled":
            self.status = "cancelled"
            self.cancel_reason = reason
            self.updated_at = datetime.now(timezone.utc)
