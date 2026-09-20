"""Orders API schemas."""

from pydantic import BaseModel, Field


class OrderItemRequest(BaseModel):
    product_id: str
    quantity: int


class OrderCreateRequest(BaseModel):
    """Create-order body.

    ``customer_id`` is accepted for compatibility but ignored: the
    authenticated JWT subject is authoritative for ownership (U5).
    """

    customer_id: str | None = Field(default=None, min_length=1, max_length=128)
    items: list[OrderItemRequest]


class OrderResponse(BaseModel):
    order_id: str
    status: str


class TimelineEventResponse(BaseModel):
    event_type: str
    occurred_at: str
    payload: dict
