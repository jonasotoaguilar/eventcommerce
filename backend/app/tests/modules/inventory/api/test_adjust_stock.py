"""Tests for AdjustStock use case and operator adjust endpoint (U1)."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.modules.inventory.application.adjust_stock import AdjustStock
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.domain.errors import (
    InsufficientStockError,
    InventoryNotFoundError,
)
from app.modules.inventory.domain.services import adjust_available_stock
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.shared.db.session import get_db_session

OPERATOR_ID = UUID("33333333-3333-3333-3333-333333333333")
SHOPPER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _user(user_id: UUID, role: str) -> CurrentUser:
    return CurrentUser(user_id=user_id, email=f"{user_id}@example.com", role=role)


class TestAdjustAvailableStock:
    def test_positive_delta(self) -> None:
        inv = Inventory(product_id="p", available_quantity=2, reserved_quantity=1)
        adjust_available_stock(inv, 3)
        assert inv.available_quantity == 5
        assert inv.reserved_quantity == 1

    def test_negative_delta_within_stock(self) -> None:
        inv = Inventory(product_id="p", available_quantity=5, reserved_quantity=1)
        adjust_available_stock(inv, -5)
        assert inv.available_quantity == 0

    def test_negative_delta_below_zero_raises(self) -> None:
        inv = Inventory(product_id="p", available_quantity=2, reserved_quantity=0)
        with pytest.raises(InsufficientStockError):
            adjust_available_stock(inv, -3)


class TestAdjustStockUseCase:
    @pytest.mark.asyncio
    async def test_adjusts_stock(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        await repo.save(
            Inventory(product_id="prod_1", available_quantity=2, reserved_quantity=0)
        )
        inv = await AdjustStock(repo).execute("prod_1", 3)
        assert inv.available_quantity == 5

    @pytest.mark.asyncio
    async def test_missing_product_raises_not_found(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        with pytest.raises(InventoryNotFoundError):
            await AdjustStock(repo).execute("missing", 1)

    @pytest.mark.asyncio
    async def test_missing_is_distinct_from_insufficient_stock(
        self, db_session
    ) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        with pytest.raises(InventoryNotFoundError) as exc_info:
            await AdjustStock(repo).execute("missing", 1)
        assert not isinstance(exc_info.value, InsufficientStockError)

    @pytest.mark.asyncio
    async def test_overdraw_raises(self, db_session) -> None:
        repo = SqlAlchemyInventoryRepository(db_session)
        await repo.save(
            Inventory(product_id="prod_1", available_quantity=1, reserved_quantity=0)
        )
        with pytest.raises(InsufficientStockError):
            await AdjustStock(repo).execute("prod_1", -2)


@pytest.fixture
def auth() -> dict:
    return {"user": _user(OPERATOR_ID, "operator")}


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


class TestAdjustStockEndpoint:
    def _seed(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/catalog",
            json={"id": "prod_1", "name": "A", "price": "5.00", "currency": "USD"},
        )
        assert response.status_code == 201

    def test_operator_adjusts_stock(self, client: TestClient) -> None:
        self._seed(client)

        response = client.post("/api/v1/inventory/prod_1/adjust", json={"delta": 7})

        assert response.status_code == 200
        assert response.json() == {
            "product_id": "prod_1",
            "available_quantity": 7,
            "reserved_quantity": 0,
        }

    def test_overdraw_returns_422(self, client: TestClient) -> None:
        self._seed(client)

        response = client.post("/api/v1/inventory/prod_1/adjust", json={"delta": -1})

        assert response.status_code == 422

    def test_missing_product_returns_404(self, client: TestClient) -> None:
        response = client.post("/api/v1/inventory/missing/adjust", json={"delta": 1})

        assert response.status_code == 404
        assert response.json() == {"detail": "Product missing not found"}

    def test_overdraw_keeps_422_envelope(self, client: TestClient) -> None:
        self._seed(client)

        response = client.post("/api/v1/inventory/prod_1/adjust", json={"delta": -5})

        assert response.status_code == 422
        assert response.json() == {"detail": "Not enough stock available"}

    def test_shopper_returns_403(self, client: TestClient, auth) -> None:
        self._seed(client)
        auth["user"] = _user(SHOPPER_ID, "shopper")

        response = client.post("/api/v1/inventory/prod_1/adjust", json={"delta": 1})

        assert response.status_code == 403

    def test_anonymous_returns_401(self, client: TestClient, app) -> None:
        app.dependency_overrides.pop(get_current_user)

        response = client.post("/api/v1/inventory/prod_1/adjust", json={"delta": 1})

        assert response.status_code == 401
