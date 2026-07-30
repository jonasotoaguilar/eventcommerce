"""Tests for inventory domain services."""

import pytest

from app.modules.inventory.domain.errors import InsufficientStockError
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.domain.services import reserve_stock


class TestReserveStock:
    def test_reserves_successfully(self) -> None:
        inv = Inventory(product_id="p1", available_quantity=10, reserved_quantity=0)
        reserve_stock(inv, 3)
        assert inv.available_quantity == 7
        assert inv.reserved_quantity == 3

    def test_insufficient_stock_raises(self) -> None:
        inv = Inventory(product_id="p1", available_quantity=1, reserved_quantity=0)
        with pytest.raises(InsufficientStockError):
            reserve_stock(inv, 3)
