"""Operator catalog API tests (U2: GET /api/v1/operator/catalog).

Operator-only read listing inactive products with stock; a product
without an inventory row reports null quantities. The public
``GET /api/v1/catalog`` still returns active products only.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
import pytest

from app.app import create_app
from app.modules.catalog.domain.entities import Product
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.shared.db.session import get_db_session

OPERATOR_ID = UUID("33333333-3333-3333-3333-333333333333")
SHOPPER_ID = UUID("11111111-1111-1111-1111-111111111111")


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


def _seed_product(engine, product_id: str, *, active: bool = True) -> None:
    async def _go() -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            now = datetime.now(timezone.utc)
            await SqlAlchemyProductRepository(session).save(
                Product(
                    id=product_id,
                    name=f"Product {product_id}",
                    description="A description",
                    price=Decimal("19.99"),
                    currency="USD",
                    active=active,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

    asyncio.run(_go())


def _seed_inventory(engine, product_id: str, *, available: int, reserved: int) -> None:
    async def _go() -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            await SqlAlchemyInventoryRepository(session).save(
                Inventory(
                    product_id=product_id,
                    available_quantity=available,
                    reserved_quantity=reserved,
                )
            )
            await session.commit()

    asyncio.run(_go())


class TestOperatorCatalog:
    def test_operator_sees_inactive_product_with_stock(
        self, client: TestClient, engine
    ) -> None:
        _seed_product(engine, "prod_active")
        _seed_product(engine, "prod_hidden", active=False)
        _seed_inventory(engine, "prod_hidden", available=4, reserved=2)

        response = client.get("/api/v1/operator/catalog")

        assert response.status_code == 200
        rows = response.json()
        assert [row["product_id"] for row in rows] == ["prod_active", "prod_hidden"]
        hidden = rows[1]
        assert hidden["active"] is False
        assert hidden["name"] == "Product prod_hidden"
        assert hidden["description"] == "A description"
        assert Decimal(hidden["price"]) == Decimal("19.99")
        assert hidden["currency"] == "USD"
        assert hidden["available_quantity"] == 4
        assert hidden["reserved_quantity"] == 2
        assert set(hidden) == {
            "product_id",
            "name",
            "description",
            "price",
            "currency",
            "active",
            "available_quantity",
            "reserved_quantity",
        }

    def test_null_stock_without_inventory_row(self, client: TestClient, engine) -> None:
        _seed_product(engine, "prod_lonely")

        response = client.get("/api/v1/operator/catalog")

        assert response.status_code == 200
        (row,) = response.json()
        assert row["product_id"] == "prod_lonely"
        assert row["available_quantity"] is None
        assert row["reserved_quantity"] is None

    def test_limit_and_offset(self, client: TestClient, engine) -> None:
        for pid in ("prod_a", "prod_b", "prod_c"):
            _seed_product(engine, pid)

        response = client.get(
            "/api/v1/operator/catalog", params={"limit": 1, "offset": 1}
        )

        assert response.status_code == 200
        (row,) = response.json()
        assert row["product_id"] == "prod_b"

    def test_anonymous_returns_401(self, client: TestClient, app) -> None:
        app.dependency_overrides.pop(get_current_user)

        response = client.get("/api/v1/operator/catalog")

        assert response.status_code == 401
        assert "detail" in response.json()

    def test_shopper_returns_403(self, client: TestClient, auth) -> None:
        auth["user"] = _user(SHOPPER_ID)

        response = client.get("/api/v1/operator/catalog")

        assert response.status_code == 403
        assert "detail" in response.json()

    def test_limit_bounds_return_422(self, client: TestClient) -> None:
        assert (
            client.get("/api/v1/operator/catalog", params={"limit": 0}).status_code
            == 422
        )
        assert (
            client.get("/api/v1/operator/catalog", params={"limit": 201}).status_code
            == 422
        )

    def test_negative_offset_returns_422(self, client: TestClient) -> None:
        assert (
            client.get("/api/v1/operator/catalog", params={"offset": -1}).status_code
            == 422
        )


class TestPublicCatalogRegression:
    def test_public_catalog_returns_active_only_for_anonymous(
        self, client: TestClient, app, engine
    ) -> None:
        _seed_product(engine, "prod_active")
        _seed_product(engine, "prod_hidden", active=False)
        app.dependency_overrides.pop(get_current_user)

        response = client.get("/api/v1/catalog")

        assert response.status_code == 200
        assert [row["id"] for row in response.json()] == ["prod_active"]
