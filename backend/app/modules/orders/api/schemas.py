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


class OrderCancelRequest(BaseModel):
    """Operator cancel body: validated reason with a stable default.

    The orders contract carries ``cancel_reason`` as free text, so the
    operator path defaults to ``operator_cancelled`` instead of
    inventing a bounded enum (U4).
    """

    reason: str = Field(default="operator_cancelled", min_length=1, max_length=128)


class OrderConfirmResponse(BaseModel):
    order_id: str
    status: str


class OrderCancelResponse(BaseModel):
    order_id: str
    status: str
    cancel_reason: str | None = None


class TimelineEventResponse(BaseModel):
    event_type: str
    occurred_at: str
    payload: dict
