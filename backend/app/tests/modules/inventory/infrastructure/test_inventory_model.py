"""Tests for inventory ORM models."""

from app.modules.inventory.infrastructure.models import InventoryModel


class TestInventoryModel:
    def test_inventory_columns(self) -> None:
        cols = {c.name for c in InventoryModel.__table__.columns}
        assert "product_id" in cols
        assert "available_quantity" in cols
        assert "reserved_quantity" in cols
