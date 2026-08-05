"""Checkout API schemas (design.md API and Data Contracts).

CheckoutRequest carries customer/product IDs 1-128 chars, 1-100 unique
items, quantity 1-10,000, a Decimal amount 0-999,999,999.99 with at most
two decimals, a currency normalized then validated syntactically as exactly
three uppercase ASCII letters (syntactic ISO 4217 — this does NOT prove a
currency exists; catalog/reconciliation is deferred), and an optional
visible-ASCII Idempotency-Key 1-128 chars. CheckoutResponse carries
order_id, status, nullable cancel_reason, and nullable payment_status.
"""

import re
from decimal import Decimal
from typing import Self

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
    """Validated body of ``POST /api/v1/checkout``."""

    customer_id: str = Field(min_length=1, max_length=128)
    items: list[CheckoutItemRequest] = Field(min_length=1, max_length=MAX_ITEMS)
    amount: Decimal = Field(ge=Decimal("0"), le=MAX_AMOUNT)
    currency: str
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("currency")
    @classmethod
    def _normalize_and_validate_currency(cls, value: str) -> str:
        normalized = value.upper()
        if CURRENCY_PATTERN.fullmatch(normalized) is None:
            raise ValueError("currency must be exactly three uppercase ASCII letters")
        return normalized

    @field_validator("amount")
    @classmethod
    def _at_most_two_decimal_places(cls, value: Decimal) -> Decimal:
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
    def _items_are_unique(self) -> Self:
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
