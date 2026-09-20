"""Cart API schemas.

Request bodies never carry a customer id: ownership always comes from
the verified JWT subject, so a stray ``customer_id`` key is ignored by
Pydantic rather than trusted.
"""

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class AddCartItemRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=128)
    quantity: int = Field(ge=1, le=10_000)


class SetCartItemQuantityRequest(BaseModel):
    quantity: int = Field(ge=1, le=10_000)


class CartLineResponse(BaseModel):
    product_id: str
    name: str
    quantity: int
    unit_price: Decimal
    currency: str
    line_total: Decimal


class CartResponse(BaseModel):
    cart_id: UUID
    customer_id: UUID
    items: list[CartLineResponse] = Field(default_factory=list)
    subtotal: Decimal
    currency: str | None = None
