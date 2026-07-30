"""Order domain events."""

from dataclasses import dataclass, field
from uuid import UUID

from app.modules.orders.domain.entities import OrderItem
from app.shared.events.domain import DomainEvent


@dataclass(frozen=True)
class OrderCreated(DomainEvent):
    """Event emitted when a new order is created."""

    customer_id: str
    items: list[OrderItem] = field(default_factory=list)

    @property
    def order_id(self) -> UUID:
        return self.aggregate_id


@dataclass(frozen=True)
class InventoryReserved(DomainEvent):
    """Event emitted when inventory is successfully reserved for an order."""

    result: str = "reserved"

    @property
    def order_id(self) -> UUID:
        return self.aggregate_id


@dataclass(frozen=True)
class InventoryRejected(DomainEvent):
    """Event emitted when inventory reservation fails for an order."""

    result: str = "rejected"
    reason: str = ""

    @property
    def order_id(self) -> UUID:
        return self.aggregate_id
