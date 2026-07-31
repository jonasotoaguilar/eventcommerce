"""Inventory domain entities."""

from dataclasses import dataclass


@dataclass
class Inventory:
    product_id: str
    available_quantity: int
    reserved_quantity: int


@dataclass(frozen=True)
class StockQuantity:
    amount: int
