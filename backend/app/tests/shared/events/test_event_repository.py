"""Integration tests for shared SQLAlchemy event repository."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.shared.events.event_repository import SqlAlchemyEventRepository


class TestSqlAlchemyEventRepository:
    @pytest.mark.asyncio
    async def test_add_and_get_timeline(self, db_session) -> None:
        repo = SqlAlchemyEventRepository(db_session)

        await repo.add(
            event_id=uuid4(),
            aggregate_type="order",
            aggregate_id="order-123",
            event_type="OrderCreated",
            occurred_at=datetime.now(timezone.utc),
            payload={"customer_id": "cus_1"},
        )
        await repo.add(
            event_id=uuid4(),
            aggregate_type="order",
            aggregate_id="order-123",
            event_type="InventoryReserved",
            occurred_at=datetime.now(timezone.utc),
            payload={"result": "reserved"},
        )
        await repo.add(
            event_id=uuid4(),
            aggregate_type="payment",
            aggregate_id="pay-456",
            event_type="PaymentAuthorized",
            occurred_at=datetime.now(timezone.utc),
            payload={"amount": 100},
        )

        timeline = await repo.get_timeline(
            aggregate_type="order", aggregate_id="order-123"
        )
        assert len(timeline) == 2
        assert timeline[0].event_type == "OrderCreated"
        assert timeline[0].payload["customer_id"] == "cus_1"
        assert timeline[1].event_type == "InventoryReserved"

    @pytest.mark.asyncio
    async def test_get_timeline_empty(self, db_session) -> None:
        repo = SqlAlchemyEventRepository(db_session)
        timeline = await repo.get_timeline(
            aggregate_type="order", aggregate_id="nonexistent"
        )
        assert timeline == []

    @pytest.mark.asyncio
    async def test_add_with_uuid_and_datetime_payload(self, db_session) -> None:
        repo = SqlAlchemyEventRepository(db_session)
        nested_uuid = uuid4()
        nested_dt = datetime.now(timezone.utc)

        await repo.add(
            event_id=uuid4(),
            aggregate_type="order",
            aggregate_id="order-789",
            event_type="ComplexEvent",
            occurred_at=datetime.now(timezone.utc),
            payload={
                "uuid": nested_uuid,
                "dt": nested_dt,
                "items": [{"id": nested_uuid}],
            },
        )

        timeline = await repo.get_timeline(
            aggregate_type="order", aggregate_id="order-789"
        )
        assert len(timeline) == 1
        assert timeline[0].payload["uuid"] == str(nested_uuid)
        assert timeline[0].payload["dt"] == nested_dt.isoformat()
        assert timeline[0].payload["items"][0]["id"] == str(nested_uuid)
