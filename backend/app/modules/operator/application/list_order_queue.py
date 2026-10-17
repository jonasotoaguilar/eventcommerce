"""ListOrderQueue use case (operator order-queue read model).

Composes the delivered orders and payments contexts without adding a
dependency between them: the queue reads orders via
``OrderRepository.list_queue`` and projects each row's money from the
latest payment row for that order (by ``created_at``, id tie-break).
Orders keep no amount or currency; when an order has no payment row
both fields stay null rather than defaulting to zero.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.modules.orders.domain.repository import OrderRepository
from app.modules.payments.domain.entities import Payment
from app.modules.payments.domain.repository import PaymentRepository


@dataclass(frozen=True)
class OrderQueueRow:
    order_id: UUID
    customer_id: str
    status: str
    created_at: datetime
    cancel_reason: str | None
    item_count: int
    total: Decimal | None
    currency: str | None


class ListOrderQueue:
    def __init__(
        self,
        order_repository: OrderRepository,
        payment_repository: PaymentRepository,
    ) -> None:
        self._orders = order_repository
        self._payments = payment_repository

    async def execute(
        self,
        status: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OrderQueueRow]:
        orders = await self._orders.list_queue(
            status=status,
            created_from=created_from,
            created_to=created_to,
            limit=limit,
            offset=offset,
        )
        payments = await self._payments.list_by_order_ids([o.id for o in orders])
        latest: dict[UUID, Payment] = {}
        for payment in payments:
            current = latest.get(payment.order_id)
            if current is None or (payment.created_at, payment.id) > (
                current.created_at,
                current.id,
            ):
                latest[payment.order_id] = payment
        rows = []
        for order in orders:
            payment = latest.get(order.id)
            rows.append(
                OrderQueueRow(
                    order_id=order.id,
                    customer_id=order.customer_id,
                    status=order.status,
                    created_at=order.created_at,
                    cancel_reason=order.cancel_reason,
                    item_count=sum(item.quantity for item in order.items),
                    total=payment.amount if payment is not None else None,
                    currency=payment.currency if payment is not None else None,
                )
            )
        return rows
