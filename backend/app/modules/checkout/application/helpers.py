"""Response serialization and key-hash helpers for the checkout core."""

import hashlib
from typing import Any

from app.modules.checkout.api.schemas import CheckoutResponse
from app.modules.orders.domain.entities import Order


def serialize_response(order: Order, payment_status: str | None) -> dict[str, Any]:
    """Map a terminal order to the ``CheckoutResponse`` body dict.

    The body is the exact JSON the durable replay cache stores, so a
    replay returns byte-identical content.
    """
    return CheckoutResponse(
        order_id=str(order.id),
        status=order.status,
        cancel_reason=order.cancel_reason,
        payment_status=payment_status,
    ).model_dump()


def hash_key(key: str) -> str:
    """Short SHA-256 prefix of an idempotency key, safe for logs.

    Raw keys and payloads are never logged; only this 8-hex-char prefix
    identifies a request in observability output.
    """
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
