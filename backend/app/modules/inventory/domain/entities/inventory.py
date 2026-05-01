"""Inventory domain entity."""
from dataclasses import dataclass


@dataclass
class Inventory:
    product_id: str
    available_quantity: int
    reserved_quantity: int

