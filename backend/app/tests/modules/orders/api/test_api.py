"""API integration tests for orders router."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.app import create_app
from app.shared.db.session import get_db_session
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.fixture
def client(engine):
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    app = create_app()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_session
    yield TestClient(app)


class TestOrdersAPI:
    def test_create_order(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/orders",
            json={
                "customer_id": "cus_1",
                "items": [{"product_id": "prod_1", "quantity": 2}],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "order_id" in data
        assert data["status"] == "pending"

    def test_get_order(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/v1/orders",
            json={
                "customer_id": "cus_1",
                "items": [{"product_id": "prod_1", "quantity": 2}],
            },
        )
        order_id = create_resp.json()["order_id"]

        get_resp = client.get(f"/api/v1/orders/{order_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["status"] == "pending"
        assert data["customer_id"] == "cus_1"

    def test_get_order_not_found(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/orders/{uuid4()}")
        assert response.status_code == 404

    def test_get_timeline(self, client: TestClient) -> None:
        create_resp = client.post(
            "/api/v1/orders",
            json={
                "customer_id": "cus_1",
                "items": [{"product_id": "prod_1", "quantity": 2}],
            },
        )
        order_id = create_resp.json()["order_id"]

        timeline_resp = client.get(f"/api/v1/orders/{order_id}/timeline")
        assert timeline_resp.status_code == 200
        data = timeline_resp.json()
        assert len(data) >= 1
        assert data[0]["event_type"] == "OrderCreated"
