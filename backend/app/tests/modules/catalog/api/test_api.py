"""API boundary tests for the catalog router (U1).

Public ``GET /api/v1/catalog`` browse and detail expose only active
products; operator writes require role ``operator`` (401 anonymous,
403 non-operator) and follow the ``{"detail": ...}`` error envelope.
"""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.shared.db.session import get_db_session

OPERATOR_ID = UUID("33333333-3333-3333-3333-333333333333")
SHOPPER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _user(user_id: UUID, role: str) -> CurrentUser:
    return CurrentUser(user_id=user_id, email=f"{user_id}@example.com", role=role)


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


def _payload(product_id: str = "prod_1", **overrides) -> dict:
    body: dict = {
        "id": product_id,
        "name": "Workshop Ticket",
        "price": "49.99",
        "currency": "USD",
    }
    body.update(overrides)
    return body


def _create(client: TestClient, **overrides) -> dict:
    response = client.post("/api/v1/catalog", json=_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


class TestPublicBrowse:
    def test_empty_list(self, client: TestClient) -> None:
        assert client.get("/api/v1/catalog").json() == []

    def test_lists_only_active_products(self, client: TestClient) -> None:
        _create(client, product_id="prod_visible")
        _create(client, product_id="prod_hidden", active=False)

        response = client.get("/api/v1/catalog")

        assert response.status_code == 200
        assert [p["id"] for p in response.json()] == ["prod_visible"]

    def test_detail_returns_active_product(self, client: TestClient) -> None:
        _create(client)

        response = client.get("/api/v1/catalog/prod_1")

        assert response.status_code == 200
        assert response.json()["price"] == "49.99"

    def test_detail_missing_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/catalog/missing")

        assert response.status_code == 404
        assert response.json() == {"detail": "Product not found"}

    def test_detail_inactive_returns_404(self, client: TestClient) -> None:
        _create(client, product_id="prod_hidden", active=False)

        response = client.get("/api/v1/catalog/prod_hidden")

        assert response.status_code == 404

    def test_public_reads_need_no_auth(self, client: TestClient, app) -> None:
        _create(client)
        app.dependency_overrides.pop(get_current_user)

        assert client.get("/api/v1/catalog").status_code == 200
        assert client.get("/api/v1/catalog/prod_1").status_code == 200


class TestOperatorWrites:
    def test_create_seeds_inventory_at_zero(self, client: TestClient) -> None:
        created = _create(client)

        assert created["id"] == "prod_1"
        assert created["active"] is True

        stock = client.post("/api/v1/inventory/prod_1/adjust", json={"delta": 0})
        assert stock.status_code == 200
        assert stock.json()["available_quantity"] == 0

    def test_create_duplicate_returns_409(self, client: TestClient) -> None:
        _create(client)

        response = client.post("/api/v1/catalog", json=_payload())

        assert response.status_code == 409

    def test_create_invalid_price_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/catalog", json=_payload(price="10.999"))

        assert response.status_code == 422

    def test_create_lowercase_currency_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/catalog", json=_payload(currency="usd"))

        assert response.status_code == 422

    def test_update_product(self, client: TestClient) -> None:
        _create(client)

        response = client.patch("/api/v1/catalog/prod_1", json={"name": "Renamed"})

        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"

    def test_update_missing_returns_404(self, client: TestClient) -> None:
        response = client.patch("/api/v1/catalog/missing", json={"name": "X"})

        assert response.status_code == 404
        assert response.json() == {"detail": "Product not found"}

    def test_shopper_create_returns_403(self, client: TestClient, auth) -> None:
        auth["user"] = _user(SHOPPER_ID, "shopper")

        response = client.post("/api/v1/catalog", json=_payload())

        assert response.status_code == 403

    def test_shopper_update_returns_403(self, client: TestClient, auth) -> None:
        _create(client)
        auth["user"] = _user(SHOPPER_ID, "shopper")

        response = client.patch("/api/v1/catalog/prod_1", json={"name": "X"})

        assert response.status_code == 403

    def test_anonymous_write_returns_401(self, client: TestClient, app) -> None:
        app.dependency_overrides.pop(get_current_user)

        assert client.post("/api/v1/catalog", json=_payload()).status_code == 401
        assert (
            client.patch("/api/v1/catalog/prod_1", json={"name": "X"}).status_code
            == 401
        )
