"""Orders API schemas."""
from pydantic import BaseModel


class OrderCreateRequest(BaseModel):
    customer_id: str
    items: list[dict]


class OrderResponse(BaseModel):
    order_id: str
    status: str

