"""Stock quantity value object."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StockQuantity:
    amount: int
