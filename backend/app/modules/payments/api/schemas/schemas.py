"""Payments API schemas."""
from pydantic import BaseModel


class PaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    status: str
    amount: float
    currency: str

