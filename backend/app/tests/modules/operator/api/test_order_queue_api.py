"""Operator order-queue API tests (U1: GET /api/v1/operator/orders).

The queue is operator-only, supports status/date filters with
limit/offset pagination, and projects totals from the latest payment
row per order (null when the order has no payment).
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.infrastructure.models import OrderModel
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.modules.payments.domain.entities import Payment
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)
from app.shared.db.session import get_db_session

OWNER_ID = UUID("11111111-1111-1111-1111-111111111111")
OPERATOR_ID = UUID("33333333-3333-3333-3333-333333333333")

FIRST = datetime(2024, 5, 1, 12, 0, 0)
SECOND = datetime(2024, 5, 2, 12, 0, 0)
THIRD = datetime(2024, 5, 3, 12, 0, 0)


def _user(user_id: UUID, role: str = "shopper") -> CurrentUser:
    return CurrentUser(user_id=user_id, email=f"{user_id}@example.com", role=role)


@pytest.fixture
def auth() -> dict:
    return {"user": _user(OPERATOR_ID, role="operator")}


@pytest.fixture
def app(engine, auth):
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    async def override_current_user():
        return auth["user"]

    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_current_user
    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def _seed_order(
    engine,
    *,
    status: str = "pending",
    created_at: datetime = FIRST,
    quantity: int = 1,
    customer_id: str = "cus_1",
) -> UUID:
    order_id = uuid4()

    async def _go() -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            repo = SqlAlchemyOrderRepository(session)
            await repo.save(
                Order(
                    id=order_id,
                    customer_id=customer_id,
                    status="pending",
                    cancel_reason=None,
                    created_at=created_at,
                    updated_at=created_at,
                    items=[OrderItem(product_id="prod_1", quantity=quantity)],
                )
            )
            await session.flush()
            orm = (
                await session.execute(
                    select(OrderModel).where(OrderModel.id == order_id)
                )
            ).scalar_one()
            orm.status = status
            orm.created_at = created_at
            await session.commit()

    asyncio.run(_go())
    return order_id


def _seed_payment(
    engine,
    order_id: UUID,
    *,
    amount: str = "42.50",
    currency: str = "USD",
    created_at: datetime = FIRST,
) -> None:
    async def _go() -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            repo = SqlAlchemyPaymentRepository(session)
            await repo.save(
                Payment(
                    id=uuid4(),
                    order_id=order_id,
                    status="authorized",
                    amount=Decimal(amount),
                    currency=currency,
                    created_at=created_at,
                )
            )
            await session.commit()

    asyncio.run(_go())


class TestOperatorQueue:
    def test_queue_filters_by_status_and_date_with_pagination(
        self, client: TestClient, engine
    ) -> None:
        first = _seed_order(engine, status="pending", created_at=FIRST)
        second = _seed_order(engine, status="confirmed", created_at=SECOND)
        third = _seed_order(engine, status="confirmed", created_at=THIRD)

        response = client.get(
            "/api/v1/operator/orders",
            params={
                "status": "confirmed",
                "created_from": "2024-05-01T00:00:00",
                "limit": 1,
                "offset": 1,
            },
        )

        assert response.status_code == 200
        (row,) = response.json()
        assert row["order_id"] == str(third)
        assert row["customer_id"] == "cus_1"
        assert row["status"] == "confirmed"
        assert row["cancel_reason"] is None
        assert set(row) == {
            "order_id",
            "customer_id",
            "status",
            "created_at",
            "cancel_reason",
            "item_count",
            "total",
            "currency",
        }
        assert first != second

    def test_totals_projected_from_latest_payment(
        self, client: TestClient, engine
    ) -> None:
        order_id = _seed_order(engine, status="pending", quantity=2)
        _seed_payment(engine, order_id, amount="10.00", created_at=FIRST)
        _seed_payment(engine, order_id, amount="42.50", created_at=SECOND)

        response = client.get("/api/v1/operator/orders")

        assert response.status_code == 200
        (row,) = response.json()
        assert row["order_id"] == str(order_id)
        assert row["item_count"] == 2
        assert Decimal(row["total"]) == Decimal("42.50")
        assert row["currency"] == "USD"

    def test_totals_null_without_payment(self, client: TestClient, engine) -> None:
        order_id = _seed_order(engine, status="pending")

        response = client.get("/api/v1/operator/orders")

        assert response.status_code == 200
        (row,) = response.json()
        assert row["order_id"] == str(order_id)
        assert row["total"] is None
        assert row["currency"] is None

    def test_anonymous_returns_401(self, client: TestClient, app) -> None:
        app.dependency_overrides.pop(get_current_user)

        response = client.get("/api/v1/operator/orders")

        assert response.status_code == 401
        assert "detail" in response.json()

    def test_shopper_returns_403(self, client: TestClient, auth) -> None:
        auth["user"] = _user(OWNER_ID)

        response = client.get("/api/v1/operator/orders")

        assert response.status_code == 403
        assert "detail" in response.json()

    def test_unknown_status_returns_422(self, client: TestClient) -> None:
        response = client.get("/api/v1/operator/orders", params={"status": "shipped"})

        assert response.status_code == 422

    def test_malformed_date_returns_422(self, client: TestClient) -> None:
        response = client.get(
            "/api/v1/operator/orders", params={"created_from": "not-a-date"}
        )

        assert response.status_code == 422
