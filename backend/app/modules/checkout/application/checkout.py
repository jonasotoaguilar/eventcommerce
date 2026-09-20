"""Checkout orchestration use case (S3c1 + U3 cart-backed checkout).

The orchestrator owns **exactly one** terminal order transition per
request. Inner use cases (``CreateOrder``, inventory lock/reserve,
``AuthorizePayment``, ``ProcessPaymentFailure``, ``ReleaseInventory``)
never confirm or cancel; only this class calls ``Order.confirm`` /
``Order.cancel``. The AMQP-path inventory-result use case is NOT invoked
here — it stays the AMQP-path owner.

One request runs in one database transaction: claim (when an
``Idempotency-Key`` is present) → resolve inputs (inline shape as-is, or
cart id projected onto live active catalog data) → create order →
lock+reserve inventory → authorize+persist payment → confirm (+ clear the
cart) OR release+cancel (cart left intact) → cache the terminal response
→ COMMIT. The post-commit notification intent runs in a separate
transaction and is best effort: a notification failure is logged and
never rolls back the committed commerce.

Cart-backed notes (U3): the claim hash covers the stable request shape
(``cart_id`` + owner, never caller amounts), so an idempotent replay
returns the cached response without re-executing commerce and without
touching cart state. Cart lines are cleared only on the confirm path, in
the same transaction as the commerce commit.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.application.cart_view import build_cart_view
from app.modules.cart.domain.repository import CartRepository
from app.modules.catalog.domain.entities import Product
from app.modules.catalog.domain.repository import ProductRepository
from app.modules.checkout.api.schemas import MAX_AMOUNT, CheckoutRequest
from app.modules.checkout.application.errors import (
    CartCurrencyMismatchError,
    CartNotFoundError,
    CartTotalExceededError,
    EmptyCartError,
    IdempotencyConflictError,
)
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
    not part of the payload identity. ``cart_id`` is stringified because
    the canonical JSON layer only handles Decimal specially; this keeps
    the cart shape distinct from any inline shape consistently.
    """
    payload = request.model_dump(exclude={"idempotency_key"})
    if payload.get("cart_id") is not None:
        payload["cart_id"] = str(payload["cart_id"])
    return payload


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
        cart_repo: CartRepository | None = None,
        product_repo: ProductRepository | None = None,
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
        self._cart_repo = cart_repo
        self._product_repo = product_repo

    async def execute(self, request: CheckoutRequest) -> CheckoutResult:
        customer_id = request.customer_id
        if customer_id is None:
            raise ValueError("customer_id is required")
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

        cart_id_to_clear: UUID | None = None
        if request.cart_id is not None:
            (
                order_items,
                lines,
                amount,
                currency,
                cart_id_to_clear,
            ) = await self._resolve_cart_inputs(customer_id, request.cart_id)
        else:
            if (
                request.items is None
                or request.amount is None
                or request.currency is None
            ):
                raise ValueError(
                    "items, amount, and currency are required when cart_id is absent"
                )
            order_items = [
                OrderItem(product_id=item.product_id, quantity=item.quantity)
                for item in request.items
            ]
            lines = [(item.product_id, item.quantity) for item in request.items]
            amount = request.amount
            currency = request.currency

        order = await self._create_order.execute(
            customer_id=customer_id,
            items=order_items,
        )
        payment_status: str | None = None
        try:
            locked = await self._inventory_repo.lock_and_check_availability(lines)
            quantities = dict(lines)
            for inventory in locked:
                reserve_stock(inventory, quantities[inventory.product_id])
                await self._inventory_repo.save(inventory)
            payment = await self._authorize_payment.execute(order.id, amount, currency)
            payment_status = payment.status
        except InsufficientStockError:
            await self._cancel_order(order, reason=CANCEL_REASON_INSUFFICIENT_STOCK)
        except PaymentRejectedError:
            await self._process_payment_failure.execute(
                order.id,
                amount,
                currency,
                reason=CANCEL_REASON_PAYMENT_DECLINED,
            )
            payment_status = PAYMENT_STATUS_DECLINED
            release = ReleaseInventory(self._inventory_repo)
            for product_id, quantity in lines:
                await release.execute(product_id, quantity)
            await self._cancel_order(order, reason=CANCEL_REASON_PAYMENT_DECLINED)
        else:
            await self._confirm_order(order)
            if cart_id_to_clear is not None:
                if self._cart_repo is None:
                    raise ValueError("cart checkout is not configured")
                await self._cart_repo.clear_lines(cart_id_to_clear)

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

    async def _resolve_cart_inputs(
        self, customer_id: str, cart_id: UUID
    ) -> tuple[list[OrderItem], list[tuple[str, int]], Decimal, str, UUID]:
        """Project one owned cart onto authoritative order inputs.

        Only active catalog products are projected (via the shared
        ``build_cart_view`` helper); caller amounts are never trusted.
        Missing/not-owned carts share one stable 404; empty (or fully
        hidden) carts and mixed currencies are stable 422s.
        """
        if self._cart_repo is None or self._product_repo is None:
            raise ValueError("cart checkout is not configured")
        try:
            owner = UUID(customer_id)
        except ValueError:
            raise CartNotFoundError("Cart not found") from None
        cart = await self._cart_repo.get_by_id(cart_id)
        if cart is None or cart.customer_id != owner:
            raise CartNotFoundError("Cart not found")
        stored = await self._cart_repo.list_lines(cart.id)
        if not stored:
            raise EmptyCartError("Cart is empty")
        catalog: dict[str, Product] = {}
        for line in stored:
            product = await self._product_repo.get_by_id(line.product_id)
            if product is not None and product.active:
                catalog[line.product_id] = product
        view = build_cart_view(cart, stored, catalog)
        if not view.items:
            raise EmptyCartError("Cart is empty")
        currencies = {item.currency for item in view.items}
        if len(currencies) > 1:
            raise CartCurrencyMismatchError("Cart contains mixed currencies")
        if view.subtotal > MAX_AMOUNT:
            raise CartTotalExceededError("Cart total exceeds maximum amount")
        currency = view.currency
        if currency is None:
            raise EmptyCartError("Cart is empty")
        order_items = [
            OrderItem(product_id=item.product_id, quantity=item.quantity)
            for item in view.items
        ]
        lines = [(item.product_id, item.quantity) for item in view.items]
        return order_items, lines, view.subtotal, currency, cart.id

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
