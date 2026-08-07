"""Tests for outbox worker."""

import logging
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.shared.messaging.models import OutboxEventModel
from app.shared.messaging.outbox_worker import OutboxWorker
from app.shared.messaging.outbox_repository import SqlAlchemyOutboxRepository


class TestOutboxWorker:
    @pytest.mark.asyncio
    async def test_processes_pending_events(self, db_session, engine) -> None:
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        publisher = AsyncMock()
        worker = OutboxWorker(
            async_sessionmaker(bind=engine, expire_on_commit=False), publisher
        )

        await outbox_repo.save(
            event_type="OrderCreated",
            aggregate_id="order-123",
            payload={"customer_id": "cus_1"},
        )
        await db_session.commit()

        processed = await worker.run_once()
        assert processed == 1
        assert publisher.publish.call_count == 1

        async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
            row = (
                await session.execute(
                    select(OutboxEventModel).where(
                        OutboxEventModel.aggregate_id == "order-123"
                    )
                )
            ).scalar_one()
            assert row.status == "published"

    @pytest.mark.asyncio
    async def test_no_pending_events(self, engine) -> None:
        publisher = AsyncMock()
        worker = OutboxWorker(
            async_sessionmaker(bind=engine, expire_on_commit=False), publisher
        )

        processed = await worker.run_once()
        assert processed == 0
        assert publisher.publish.call_count == 0

    @pytest.mark.asyncio
    async def test_publish_failure_logs_leaves_row_pending_and_continues(
        self, db_session, engine, caplog
    ) -> None:
        outbox_repo = SqlAlchemyOutboxRepository(db_session)
        await outbox_repo.save(
            event_type="OrderCreated",
            aggregate_id="order-fail",
            payload={"customer_id": "cus_fail"},
        )
        await outbox_repo.save(
            event_type="OrderCreated",
            aggregate_id="order-success",
            payload={"customer_id": "cus_success"},
        )
        await db_session.commit()

        def publish(event) -> None:
            if event.aggregate_id == "order-fail":
                raise RuntimeError("broker unavailable")

        publisher = AsyncMock()
        publisher.publish.side_effect = publish
        worker = OutboxWorker(
            async_sessionmaker(bind=engine, expire_on_commit=False), publisher
        )

        with caplog.at_level(
            logging.ERROR, logger="app.shared.messaging.outbox_worker"
        ):
            processed = await worker.run_once()

        assert processed == 1
        assert "outbox_publish_failed" in caplog.text
        assert "order-fail" in caplog.text

        async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
            rows = (
                await session.execute(
                    select(OutboxEventModel).order_by(OutboxEventModel.aggregate_id)
                )
            ).scalars()
            statuses = {row.aggregate_id: row.status for row in rows}

        assert statuses == {
            "order-fail": "pending",
            "order-success": "published",
        }
