"""Checkout API schemas (design.md API and Data Contracts).

CheckoutRequest carries either the legacy inline shape (``items``,
``amount``, ``currency``) or a ``cart_id`` alone: cart-backed checkout
derives unique order lines and the authoritative Decimal amount from
live catalog prices and never trusts a caller-sent amount/currency.
Mixing ``cart_id`` with any inline field is a 422. ``customer_id`` is
accepted for compatibility but ignored: the authenticated JWT subject
is authoritative for ownership (U5). The optional visible-ASCII
Idempotency-Key (1-128 chars) keeps its existing behavior on both
shapes. CheckoutResponse carries order_id, status, nullable
cancel_reason, and nullable payment_status.
"""

import re
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_ITEMS = 100
MAX_QUANTITY = 10_000
MAX_AMOUNT = Decimal("999999999.99")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
VISIBLE_ASCII_PATTERN = re.compile(r"^[\x21-\x7E]+$")


class CheckoutItemRequest(BaseModel):
    """One product line inside a checkout request."""

    product_id: str = Field(min_length=1, max_length=128)
    quantity: int = Field(ge=1, le=MAX_QUANTITY)


class CheckoutRequest(BaseModel):
    """Validated body of ``POST /api/v1/checkout``.

    Either the legacy inline shape (``items`` + ``amount`` + ``currency``)
    or ``cart_id`` alone. ``customer_id`` is accepted for compatibility
    but ignored: the authenticated JWT subject is authoritative for
    ownership (U5).
    """

    customer_id: str | None = Field(default=None, min_length=1, max_length=128)
    cart_id: UUID | None = None
    items: list[CheckoutItemRequest] | None = Field(
        default=None, min_length=1, max_length=MAX_ITEMS
    )
    amount: Decimal | None = Field(default=None, ge=Decimal("0"), le=MAX_AMOUNT)
    currency: str | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("currency")
    @classmethod
    def _normalize_and_validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.upper()
        if CURRENCY_PATTERN.fullmatch(normalized) is None:
            raise ValueError("currency must be exactly three uppercase ASCII letters")
        return normalized

    @field_validator("amount")
    @classmethod
    def _at_most_two_decimal_places(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        exponent = value.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("amount must have at most two decimal places")
        return value

    @field_validator("idempotency_key")
    @classmethod
    def _idempotency_key_is_visible_ascii(cls, value: str | None) -> str | None:
        if value is not None and VISIBLE_ASCII_PATTERN.fullmatch(value) is None:
            raise ValueError("Idempotency-Key must be visible ASCII characters")
        return value

    @model_validator(mode="after")
    def _shape_and_items_are_valid(self) -> Self:
        if self.cart_id is not None:
            if (
                self.items is not None
                or self.amount is not None
                or self.currency is not None
            ):
                raise ValueError(
                    "cart_id cannot be combined with items, amount, or currency"
                )
            return self
        if self.items is None or self.amount is None or self.currency is None:
            raise ValueError(
                "items, amount, and currency are required when cart_id is absent"
            )
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("items must contain unique product_ids")
        return self


class CheckoutResponse(BaseModel):
    """Response body of ``POST /api/v1/checkout``."""

    order_id: str
    status: str
    cancel_reason: str | None = None
    payment_status: str | None = None
