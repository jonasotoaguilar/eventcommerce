"""Integration tests for SQLAlchemy notification repository."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.modules.notifications.domain.entities import Notification
from app.modules.notifications.infrastructure.sqlalchemy_repository import (
    SqlAlchemyNotificationRepository,
)


class TestSqlAlchemyNotificationRepository:
    @pytest.mark.asyncio
    async def test_save_and_get_by_id(self, db_session) -> None:
        repo = SqlAlchemyNotificationRepository(db_session)
        notification = Notification(
            id=uuid4(),
            order_id=uuid4(),
            channel="email",
            content="Your order has been confirmed.",
            sent_at=datetime.now(timezone.utc),
        )
        await repo.save(notification)

        found = await repo.get_by_id(notification.id)
        assert found is not None
        assert found.id == notification.id
        assert found.order_id == notification.order_id
        assert found.channel == "email"
        assert found.content == "Your order has been confirmed."

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session) -> None:
        repo = SqlAlchemyNotificationRepository(db_session)
        found = await repo.get_by_id(uuid4())
        assert found is None

    @pytest.mark.asyncio
    async def test_update_content(self, db_session) -> None:
        repo = SqlAlchemyNotificationRepository(db_session)
        notification = Notification(
            id=uuid4(),
            order_id=uuid4(),
            channel="sms",
            content="Pending",
            sent_at=datetime.now(timezone.utc),
        )
        await repo.save(notification)
        notification.content = "Shipped"
        await repo.save(notification)

        found = await repo.get_by_id(notification.id)
        assert found is not None
        assert found.content == "Shipped"
        assert found.channel == "sms"
