"""Orders API schemas."""

from pydantic import BaseModel


class OrderItemRequest(BaseModel):
    product_id: str
    quantity: int


class OrderCreateRequest(BaseModel):
    customer_id: str
    items: list[OrderItemRequest]


class OrderResponse(BaseModel):
    order_id: str
    status: str


class TimelineEventResponse(BaseModel):
    event_type: str
    occurred_at: str
    payload: dict
