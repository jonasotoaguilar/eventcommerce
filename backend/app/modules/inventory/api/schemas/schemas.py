"""Inventory API schemas."""

from pydantic import BaseModel


class InventoryResponse(BaseModel):
    product_id: str
    available_quantity: int
    reserved_quantity: int
