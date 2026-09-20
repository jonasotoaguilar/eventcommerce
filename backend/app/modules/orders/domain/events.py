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


@dataclass(frozen=True)
class OrderInventoryReserved(DomainEvent):
    """Internal order-owned event staging payment authorization.

    Emitted through the outbox after the order has durably moved to
    ``inventory_reserved``. The payments consumer authorizes against
    authoritative catalog totals only when it observes this event, so
    payment authorization can never race the order-state transition.
    """

    status: str = "inventory_reserved"

    @property
    def order_id(self) -> UUID:
        return self.aggregate_id


@dataclass(frozen=True)
class PaymentAuthorized(DomainEvent):
    """Event emitted when payment is successfully authorized for an order."""

    result: str = "authorized"

    @property
    def order_id(self) -> UUID:
        return self.aggregate_id


@dataclass(frozen=True)
class OrderPaymentAuthorized(DomainEvent):
    """Internal order-owned event staging confirmation.

    Emitted through the outbox after the order has durably moved to
    ``payment_authorized``. The orders finalizer confirms only when it
    observes this event, so confirmation can never race the order-state
    transition.
    """

    status: str = "payment_authorized"

    @property
    def order_id(self) -> UUID:
        return self.aggregate_id


@dataclass(frozen=True)
class PaymentRejected(DomainEvent):
    """Event emitted when payment authorization fails for an order."""

    result: str = "rejected"
    reason: str = ""

    @property
    def order_id(self) -> UUID:
        return self.aggregate_id
