"""ProcessOrderInventoryReserved use case (U2 expand-order-state-machine).

Payment-side consumer for the order-owned internal ``OrderInventoryReserved``
event. It derives the chargeable total exclusively from authoritative
catalog data and the order's own lines — caller payloads are never trusted —
then runs the existing deterministic ``AuthorizePayment`` and emits the
payment result through the outbox:

* ``PaymentAuthorized`` when the provider policy approves.
* ``PaymentRejected`` with a stable reason when catalog data cannot yield
  exactly one currency and a positive subtotal, or when the provider
  declines.

The use case never mutates order status and never touches inventory: it
holds no order-save path and no inventory dependency. The orders context
remains the sole owner of order transitions (U3 consumes the payment
result events).
"""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from app.modules.catalog.domain.repository import ProductRepository
from app.modules.orders.domain.entities import Order
from app.modules.orders.domain.errors import OrderNotFoundError
from app.modules.orders.domain.repository import OrderRepository
from app.modules.payments.application.authorize_payment import AuthorizePayment
from app.modules.payments.application.process_payment_failure import (
    ProcessPaymentFailure,
)
from app.modules.payments.domain.errors import PaymentRejectedError
from app.shared.messaging.idempotency import ProcessedEventStore
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository

CONSUMER_NAME = "ProcessOrderInventoryReserved"

REASON_PRODUCT_NOT_FOUND = "product_not_found"
REASON_PRODUCT_INACTIVE = "product_inactive"
REASON_MIXED_CURRENCY = "mixed_currency"
REASON_INVALID_CATALOG_DATA = "invalid_catalog_data"
REASON_INVALID_ORDER_LINES = "invalid_order_lines"
REASON_PAYMENT_DECLINED = "payment_declined"

_TERMINAL_ORDER_STATUSES = ("confirmed", "cancelled")


class ProcessOrderInventoryReserved:
    def __init__(
        self,
        order_repo: OrderRepository,
        product_repo: ProductRepository,
        authorize_payment: AuthorizePayment,
        process_failure: ProcessPaymentFailure,
        outbox: SqlAlchemyOutboxRepository,
        idempotency: ProcessedEventStore,
    ) -> None:
        self._order_repo = order_repo
        self._product_repo = product_repo
        self._authorize_payment = authorize_payment
        self._process_failure = process_failure
        self._outbox = outbox
        self._idempotency = idempotency

    async def execute(self, event_id: str, order_id: UUID) -> None:
        if await self._idempotency.is_processed(event_id, CONSUMER_NAME):
            return
        order = await self._order_repo.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(f"Order {order_id} not found")

        # Ordering/ownership guard: only an order already staged in
        # ``inventory_reserved`` may be charged. Terminal orders are done;
        # any other non-terminal state (e.g. a still-pending order) means
        # this event is out of order, so claim it without emitting rather
        # than racing the orders-owned transition.
        if order.status in _TERMINAL_ORDER_STATUSES or order.status != (
            "inventory_reserved"
        ):
            await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
            return

        reason, amount, currency = await self._derive_total(order)
        if reason is not None:
            # Fail closed: no trustworthy money exists to persist, so emit
            # the rejection without fabricating a Payment row.
            await self._outbox.save(
                event_type="PaymentRejected",
                aggregate_id=str(order.id),
                payload={
                    "result": "rejected",
                    "reason": reason,
                    "amount": None,
                    "currency": None,
                },
            )
            await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
            return

        assert amount is not None and currency is not None
        try:
            await self._authorize_payment.execute(
                order_id=order.id, amount=amount, currency=currency
            )
        except PaymentRejectedError:
            # Valid derived money, provider said no: persist the declined
            # Payment through the existing failure use case and emit.
            await self._process_failure.execute(
                order_id=order.id,
                amount=amount,
                currency=currency,
                reason=REASON_PAYMENT_DECLINED,
            )
            await self._outbox.save(
                event_type="PaymentRejected",
                aggregate_id=str(order.id),
                payload={
                    "result": "rejected",
                    "reason": REASON_PAYMENT_DECLINED,
                    "amount": f"{amount:.2f}",
                    "currency": currency,
                },
            )
            await self._idempotency.mark_processed(event_id, CONSUMER_NAME)
            return

        await self._outbox.save(
            event_type="PaymentAuthorized",
            aggregate_id=str(order.id),
            payload={
                "result": "authorized",
                "amount": f"{amount:.2f}",
                "currency": currency,
            },
        )
        await self._idempotency.mark_processed(event_id, CONSUMER_NAME)

    async def _derive_total(
        self, order: Order
    ) -> tuple[str | None, Decimal | None, str | None]:
        """Derive (reason, amount, currency) from catalog products.

        Returns ``(None, amount, currency)`` on success, or
        ``(stable_reason, None, None)`` when the catalog cannot yield
        exactly one currency and a positive two-decimal subtotal.
        """
        items = getattr(order, "items", [])
        if not items:
            return REASON_INVALID_ORDER_LINES, None, None
        currencies: set[str] = set()
        subtotal = Decimal("0.00")
        for item in items:
            product_id = getattr(item, "product_id", None)
            quantity = getattr(item, "quantity", None)
            if not isinstance(product_id, str) or not product_id:
                return REASON_INVALID_CATALOG_DATA, None, None
            if not isinstance(quantity, int) or quantity <= 0:
                return REASON_INVALID_CATALOG_DATA, None, None
            product = await self._product_repo.get_by_id(product_id)
            if product is None:
                return REASON_PRODUCT_NOT_FOUND, None, None
            if not product.active:
                return REASON_PRODUCT_INACTIVE, None, None
            try:
                price = (
                    product.price
                    if isinstance(product.price, Decimal)
                    else Decimal(str(product.price))
                )
            except (InvalidOperation, ValueError, TypeError):
                return REASON_INVALID_CATALOG_DATA, None, None
            if not price.is_finite() or price < 0:
                return REASON_INVALID_CATALOG_DATA, None, None
            exponent = price.as_tuple().exponent
            if not isinstance(exponent, int) or exponent < -2:
                return REASON_INVALID_CATALOG_DATA, None, None
            currency = getattr(product, "currency", None)
            if not isinstance(currency, str) or not currency:
                return REASON_INVALID_CATALOG_DATA, None, None
            currencies.add(currency)
            if len(currencies) > 1:
                return REASON_MIXED_CURRENCY, None, None
            subtotal += price * quantity
        if len(currencies) != 1:
            return REASON_INVALID_CATALOG_DATA, None, None
        subtotal = subtotal.quantize(Decimal("0.01"))
        if subtotal <= 0:
            return REASON_INVALID_CATALOG_DATA, None, None
        return None, subtotal, next(iter(currencies))
