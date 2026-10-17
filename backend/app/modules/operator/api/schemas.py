"""Operator API schemas (read-only queue rows)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class OrderQueueRowResponse(BaseModel):
    order_id: UUID
    customer_id: str
    status: str
    created_at: datetime
    cancel_reason: str | None
    item_count: int
    total: Decimal | None
    currency: str | None


class CatalogRowResponse(BaseModel):
    product_id: str
    name: str
    description: str | None
    price: Decimal
    currency: str
    active: bool
    available_quantity: int | None
    reserved_quantity: int | None


class PaymentSimulationResponse(BaseModel):
    order_id: UUID
    amount: Decimal
    currency: str
    approved: bool
    digest_byte: int
    approval_threshold: int
