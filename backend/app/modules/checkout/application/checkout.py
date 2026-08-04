"""Checkout orchestration use case (S3c1).

The orchestrator owns **exactly one** terminal order transition per
request. Inner use cases (``CreateOrder``, inventory lock/reserve,
``AuthorizePayment``, ``ProcessPaymentFailure``, ``ReleaseInventory``)
never confirm or cancel; only this class calls ``Order.confirm`` /
``Order.cancel``. The AMQP-path inventory-result use case is NOT invoked
here — it stays the AMQP-path owner.

One request runs in one database transaction: claim (when an
``Idempotency-Key`` is present) → create order → lock+reserve inventory →
authorize+persist payment → confirm OR release+cancel → cache the
terminal response → COMMIT. The post-commit notification intent runs in
a separate transaction and is best effort: a notification failure is
logged and never rolls back the committed commerce.
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkout.api.schemas import CheckoutRequest
from app.modules.checkout.application.errors import IdempotencyConflictError
from app.modules.checkout.application.helpers import hash_key, serialize_response
from app.modules.inventory.application.release_inventory import ReleaseInventory
from app.modules.inventory.domain.errors import InsufficientStockError
from app.modules.inventory.domain.repository import InventoryRepository
from app.modules.inventory.domain.services import reserve_stock
from app.modules.notifications.application.send_order_notification import (
    SendOrderNotification,
)
from app.modules.orders.application.create_order import CreateOrder
from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.domain.repository import OrderRepository
from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.domain.errors import PaymentRejectedError
from app.shared.messaging.idempotency import ClaimResult, ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository
from app.shared.messaging.payload_hash import payload_hash

logger = logging.getLogger(__name__)

CHECKOUT_CONSUMER_NAME = "Checkout"
NOTIFICATION_CHANNEL = "email"
CANCEL_REASON_PAYMENT_DECLINED = "payment_declined"
CANCEL_REASON_INSUFFICIENT_STOCK = "insufficient_stock"
CREATED_STATUS_CODE = 201
PAYMENT_STATUS_DECLINED = "declined"


@dataclass(frozen=True)
class CheckoutResult:
    """Terminal outcome of one checkout request."""

    status_code: int
    body: dict[str, Any]


def _request_payload_for_hash(request: CheckoutRequest) -> dict[str, Any]:
    """The request body as the idempotency payload fingerprint sees it.

    The Idempotency-Key itself is excluded: it is the dedup dimension,
    not part of the payload identity.
    """
    return request.model_dump(exclude={"idempotency_key"})


def _notification_content(order_status: str) -> str:
    if order_status == "confirmed":
        return "Your order has been confirmed"
    return "Your order could not be completed"


class Checkout:
    """Synchronous checkout orchestrator for ``POST /api/v1/checkout``."""

    def __init__(
        self,
        session: AsyncSession,
        order_repo: OrderRepository,
        create_order: CreateOrder,
        inventory_repo: InventoryRepository,
        outbox: SqlAlchemyOutboxRepository,
        idempotency: ProcessedEventStore,
        authorize_payment: AuthorizePayment,
        process_payment_failure: ProcessPaymentFailure,
        notifier: SendOrderNotification,
    ) -> None:
        self._session = session
        self._order_repo = order_repo
        self._create_order = create_order
        self._inventory_repo = inventory_repo
        self._outbox = outbox
        self._idempotency = idempotency
        self._authorize_payment = authorize_payment
        self._process_payment_failure = process_payment_failure
        self._notifier = notifier

    async def execute(self, request: CheckoutRequest) -> CheckoutResult:
        key = request.idempotency_key
        request_hash: str | None = None
        if key is not None:
            request_hash = payload_hash(_request_payload_for_hash(request))
            claim = await self._idempotency.claim(
                key, CHECKOUT_CONSUMER_NAME, request_hash
            )
            if claim is ClaimResult.REPLAY_MATCH:
                logger.info("checkout_replayed key_hash=%s", hash_key(key))
                cached = await self._idempotency.fetch_cached(
                    key, CHECKOUT_CONSUMER_NAME
                )
                if cached is None:
                    raise IdempotencyConflictError(
                        "completed claim has no cached response"
                    )
                return CheckoutResult(status_code=cached.status, body=cached.body)
            if claim is ClaimResult.CONFLICT:
                logger.info("checkout_conflict key_hash=%s", hash_key(key))
                raise IdempotencyConflictError(
                    "Idempotency-Key was reused with a different payload"
                )

        order = await self._create_order.execute(
            customer_id=request.customer_id,
            items=[
                OrderItem(product_id=item.product_id, quantity=item.quantity)
                for item in request.items
            ],
        )
        lines = [(item.product_id, item.quantity) for item in request.items]
        payment_status: str | None = None
        try:
            locked = await self._inventory_repo.lock_and_check_availability(lines)
            quantities = dict(lines)
            for inventory in locked:
                reserve_stock(inventory, quantities[inventory.product_id])
                await self._inventory_repo.save(inventory)
            payment = await self._authorize_payment.execute(
                order.id, request.amount, request.currency
            )
            payment_status = payment.status
        except InsufficientStockError:
            await self._cancel_order(order, reason=CANCEL_REASON_INSUFFICIENT_STOCK)
        except PaymentRejectedError:
            await self._process_payment_failure.execute(
                order.id,
                request.amount,
                request.currency,
                reason=CANCEL_REASON_PAYMENT_DECLINED,
            )
            payment_status = PAYMENT_STATUS_DECLINED
            release = ReleaseInventory(self._inventory_repo)
            for product_id, quantity in lines:
                await release.execute(product_id, quantity)
            await self._cancel_order(order, reason=CANCEL_REASON_PAYMENT_DECLINED)
        else:
            await self._confirm_order(order)

        response_body = serialize_response(order, payment_status)
        if key is not None and request_hash is not None:
            await self._idempotency.complete_with_response(
                key,
                CHECKOUT_CONSUMER_NAME,
                CREATED_STATUS_CODE,
                response_body,
                request_hash,
            )
        await self._session.commit()
        await self._notify_best_effort(order)
        logger.info(
            "checkout_completed order_id=%s key_hash=%s",
            order.id,
            hash_key(key) if key is not None else "",
        )
        return CheckoutResult(status_code=CREATED_STATUS_CODE, body=response_body)

    async def _confirm_order(self, order: Order) -> None:
        order.confirm()
        await self._order_repo.save(order)
        await self._outbox.save(
            event_type="OrderConfirmed",
            aggregate_id=str(order.id),
            payload={"status": "confirmed"},
        )

    async def _cancel_order(self, order: Order, *, reason: str) -> None:
        order.cancel(reason)
        await self._order_repo.save(order)
        await self._outbox.save(
            event_type="OrderCancelled",
            aggregate_id=str(order.id),
            payload={"status": "cancelled", "reason": reason},
        )

    async def _notify_best_effort(self, order: Order) -> None:
        """Emit one notification intent after commit, never roll back commerce."""
        try:
            await self._notifier.execute(
                order_id=order.id,
                channel=NOTIFICATION_CHANNEL,
                content=_notification_content(order.status),
            )
            await self._session.commit()
        except Exception:
            logger.exception("checkout_notification_failed order_id=%s", order.id)
            await self._session.rollback()
