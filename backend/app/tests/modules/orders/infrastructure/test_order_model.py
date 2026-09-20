"""Tests for orders ORM models."""

from sqlalchemy import CheckConstraint, inspect

from app.modules.orders.infrastructure.models import OrderItemModel, OrderModel
from app.shared.events.models import DomainEventModel


class TestOrderModel:
    def test_order_columns(self) -> None:
        cols = {c.name for c in OrderModel.__table__.columns}
        assert "id" in cols
        assert "customer_id" in cols
        assert "status" in cols
        assert "cancel_reason" in cols
        assert "created_at" in cols
        assert "updated_at" in cols

    def test_order_items_columns(self) -> None:
        cols = {c.name for c in OrderItemModel.__table__.columns}
        assert "id" in cols
        assert "order_id" in cols
        assert "product_id" in cols
        assert "quantity" in cols

    def test_domain_events_columns(self) -> None:
        cols = {c.name for c in DomainEventModel.__table__.columns}
        assert "id" in cols
        assert "event_id" in cols
        assert "aggregate_type" in cols
        assert "aggregate_id" in cols
        assert "event_type" in cols
        assert "payload" in cols
        assert "occurred_at" in cols

    def test_order_to_items_relationship(self) -> None:
        rels = {r.key for r in inspect(OrderModel).relationships}
        assert "items" in rels
        assert "events" not in rels

    def test_order_status_lifecycle_check_constraint(self) -> None:
        checks = {
            c.name: c.sqltext.text
            for c in OrderModel.__table__.constraints
            if isinstance(c, CheckConstraint)
        }
        assert "ck_orders_status_lifecycle" in checks
        sql = checks["ck_orders_status_lifecycle"]
        for status in (
            "pending",
            "inventory_reserved",
            "payment_authorized",
            "confirmed",
            "cancelled",
        ):
            assert status in sql

    def test_order_has_single_status_column(self) -> None:
        status_cols = [
            c.name for c in OrderModel.__table__.columns if "status" in c.name
        ]
        assert status_cols == ["status"]
