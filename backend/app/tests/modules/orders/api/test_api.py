"""U5 IAM boundary tests for the orders router (strict TDD).

Write paths derive ``customer_id`` from the authenticated JWT subject
(``CurrentUser``); reads allow only the owning customer or an operator
and return 404 otherwise to avoid an existence oracle.
"""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.shared.db.session import get_db_session

OWNER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_ID = UUID("22222222-2222-2222-2222-222222222222")
OPERATOR_ID = UUID("33333333-3333-3333-3333-333333333333")


def _user(user_id: UUID, role: str = "shopper") -> CurrentUser:
    return CurrentUser(user_id=user_id, email=f"{user_id}@example.com", role=role)


@pytest.fixture
def auth() -> dict:
    return {"user": _user(OWNER_ID)}


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


def _items_body(**overrides) -> dict:
    body: dict = {"items": [{"product_id": "prod_1", "quantity": 2}]}
    body.update(overrides)
    return body


def _create(client: TestClient) -> str:
    response = client.post("/api/v1/orders", json=_items_body())
    assert response.status_code == 201
    return response.json()["order_id"]


class TestCreateOrderDerivesSubject:
    def test_customer_id_comes_from_subject_without_body_value(
        self, client: TestClient
    ) -> None:
        order_id = _create(client)

        get_resp = client.get(f"/api/v1/orders/{order_id}")

        assert get_resp.status_code == 200
        assert get_resp.json()["customer_id"] == str(OWNER_ID)

    def test_body_customer_id_is_ignored_and_overridden(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/v1/orders",
            json=_items_body(customer_id="attacker-chosen-id"),
        )
        assert response.status_code == 201
        order_id = response.json()["order_id"]

        get_resp = client.get(f"/api/v1/orders/{order_id}")

        assert get_resp.status_code == 200
        assert get_resp.json()["customer_id"] == str(OWNER_ID)

    def test_anonymous_create_returns_401(self, client: TestClient, app) -> None:
        app.dependency_overrides.pop(get_current_user)

        response = client.post("/api/v1/orders", json=_items_body())

        assert response.status_code == 401


class TestReadAuthorization:
    def test_owner_and_operator_can_read(self, client: TestClient, auth) -> None:
        order_id = _create(client)

        assert client.get(f"/api/v1/orders/{order_id}").status_code == 200

        auth["user"] = _user(OPERATOR_ID, role="operator")
        owner_resp = client.get(f"/api/v1/orders/{order_id}")

        assert owner_resp.status_code == 200
        assert owner_resp.json()["customer_id"] == str(OWNER_ID)

    def test_cross_user_read_returns_404_not_403(
        self, client: TestClient, auth
    ) -> None:
        order_id = _create(client)

        auth["user"] = _user(OTHER_ID)
        response = client.get(f"/api/v1/orders/{order_id}")

        assert response.status_code == 404

    def test_missing_order_returns_404(self, client: TestClient) -> None:
        assert client.get(f"/api/v1/orders/{uuid4()}").status_code == 404

    def test_anonymous_read_returns_401(self, client: TestClient, app, auth) -> None:
        order_id = _create(client)

        app.dependency_overrides.pop(get_current_user)

        assert client.get(f"/api/v1/orders/{order_id}").status_code == 401


class TestTimelineAuthorization:
    def test_owner_and_operator_can_read_timeline(
        self, client: TestClient, auth
    ) -> None:
        order_id = _create(client)

        owner_resp = client.get(f"/api/v1/orders/{order_id}/timeline")
        assert owner_resp.status_code == 200
        assert owner_resp.json()[0]["event_type"] == "OrderCreated"

        auth["user"] = _user(OPERATOR_ID, role="operator")
        operator_resp = client.get(f"/api/v1/orders/{order_id}/timeline")

        assert operator_resp.status_code == 200

    def test_cross_user_timeline_returns_404(self, client: TestClient, auth) -> None:
        order_id = _create(client)

        auth["user"] = _user(OTHER_ID)

        assert client.get(f"/api/v1/orders/{order_id}/timeline").status_code == 404

    def test_anonymous_timeline_returns_401(self, client: TestClient, app) -> None:
        order_id = _create(client)

        app.dependency_overrides.pop(get_current_user)

        assert client.get(f"/api/v1/orders/{order_id}/timeline").status_code == 401
