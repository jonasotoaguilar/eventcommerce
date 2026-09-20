"""API boundary tests for the cart router (U2).

Every route requires a valid bearer JWT (401 when missing); ownership
always comes from the JWT subject — a body-sent ``customer_id`` is
ignored. Missing/inactive products share one stable 404, quantity uses
the 1..10,000 limits (422), cart conflicts surface as 409, and DELETE
is idempotent (always 200).
"""

from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.cart.infrastructure.models import CartModel  # noqa: F401
from app.modules.catalog.infrastructure.models import ProductModel
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.application.tokens import CurrentUser
from app.modules.iam.infrastructure.models import UserModel
from app.shared.db.session import get_db_session

SHOPPER_A = UUID("11111111-1111-1111-1111-111111111111")
SHOPPER_B = UUID("22222222-2222-2222-2222-222222222222")
OPERATOR = UUID("33333333-3333-3333-3333-333333333333")


def _user(user_id: UUID, role: str) -> CurrentUser:
    return CurrentUser(user_id=user_id, email=f"{user_id}@example.com", role=role)


@pytest.fixture
def auth() -> dict:
    return {"user": _user(SHOPPER_A, "shopper")}


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


async def _seed_users(engine) -> None:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        for user_id, role in (
            (SHOPPER_A, "shopper"),
            (SHOPPER_B, "shopper"),
            (OPERATOR, "operator"),
        ):
            session.add(
                UserModel(
                    id=user_id,
                    email=f"{user_id}@example.com",
                    password_hash="x",
                    role=role,
                )
            )
        await session.commit()


async def _seed_products(engine, specs: list[tuple]) -> None:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        for spec in specs:
            product_id = spec[0]
            price = spec[1] if len(spec) > 1 else "10.00"
            currency = spec[2] if len(spec) > 2 else "USD"
            active = spec[3] if len(spec) > 3 else True
            session.add(
                ProductModel(
                    id=product_id,
                    name=f"Product {product_id}",
                    description=None,
                    price=Decimal(price),
                    currency=currency,
                    active=active,
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def _prepare(engine, products=None) -> None:
    await _seed_users(engine)
    await _seed_products(engine, products or [("p1", "49.99"), ("p2", "5.00")])


class TestAuth:
    @pytest.mark.asyncio
    async def test_missing_auth_returns_401_on_every_route(
        self, client: TestClient, app, engine
    ) -> None:
        await _prepare(engine)
        app.dependency_overrides.pop(get_current_user)

        assert client.get("/api/v1/cart").status_code == 401
        assert (
            client.post(
                "/api/v1/cart/items", json={"product_id": "p1", "quantity": 1}
            ).status_code
            == 401
        )
        assert (
            client.patch("/api/v1/cart/items/p1", json={"quantity": 1}).status_code
            == 401
        )
        assert client.delete("/api/v1/cart/items/p1").status_code == 401

    @pytest.mark.asyncio
    async def test_missing_auth_uses_detail_envelope(
        self, client: TestClient, app, engine
    ) -> None:
        await _prepare(engine)
        app.dependency_overrides.pop(get_current_user)

        response = client.get("/api/v1/cart")

        assert response.status_code == 401
        assert set(response.json()) == {"detail"}

    @pytest.mark.asyncio
    async def test_body_customer_id_is_ignored(
        self, client: TestClient, engine
    ) -> None:
        await _prepare(engine)

        response = client.post(
            "/api/v1/cart/items",
            json={
                "product_id": "p1",
                "quantity": 1,
                "customer_id": str(SHOPPER_B),
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["customer_id"] == str(SHOPPER_A)


class TestGetCart:
    @pytest.mark.asyncio
    async def test_lazy_create_empty_shape(self, client: TestClient, engine) -> None:
        await _prepare(engine)

        response = client.get("/api/v1/cart")

        assert response.status_code == 200
        body = response.json()
        assert body["customer_id"] == str(SHOPPER_A)
        assert body["items"] == []
        assert body["subtotal"] == "0.00"
        assert body["currency"] is None

    @pytest.mark.asyncio
    async def test_owner_isolation(self, client: TestClient, auth, engine) -> None:
        await _prepare(engine)
        client.post("/api/v1/cart/items", json={"product_id": "p1", "quantity": 2})

        auth["user"] = _user(SHOPPER_B, "shopper")
        body = client.get("/api/v1/cart").json()

        assert body["customer_id"] == str(SHOPPER_B)
        assert body["items"] == []
        assert body["subtotal"] == "0.00"


class TestAddItem:
    @pytest.mark.asyncio
    async def test_add_returns_live_projection(
        self, client: TestClient, engine
    ) -> None:
        await _prepare(engine)

        response = client.post(
            "/api/v1/cart/items", json={"product_id": "p1", "quantity": 2}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["currency"] == "USD"
        assert body["subtotal"] == "99.98"
        (line,) = body["items"]
        assert line == {
            "product_id": "p1",
            "name": "Product p1",
            "quantity": 2,
            "unit_price": "49.99",
            "currency": "USD",
            "line_total": "99.98",
        }

    @pytest.mark.asyncio
    async def test_add_existing_line_increments(
        self, client: TestClient, engine
    ) -> None:
        await _prepare(engine)
        client.post("/api/v1/cart/items", json={"product_id": "p1", "quantity": 2})

        body = client.post(
            "/api/v1/cart/items", json={"product_id": "p1", "quantity": 3}
        ).json()

        assert body["items"][0]["quantity"] == 5
        assert body["subtotal"] == "249.95"

    @pytest.mark.asyncio
    async def test_missing_and_inactive_share_stable_404(
        self, client: TestClient, engine
    ) -> None:
        await _prepare(engine, [("hidden", "9.99", "USD", False)])

        missing = client.post(
            "/api/v1/cart/items", json={"product_id": "nope", "quantity": 1}
        )
        hidden = client.post(
            "/api/v1/cart/items", json={"product_id": "hidden", "quantity": 1}
        )

        assert missing.status_code == 404
        assert hidden.status_code == 404
        assert missing.json() == {"detail": "Product not found"}
        assert hidden.json() == missing.json()

    @pytest.mark.asyncio
    async def test_quantity_bounds_are_422(self, client: TestClient, engine) -> None:
        await _prepare(engine)

        for quantity in (0, -5, 10_001):
            response = client.post(
                "/api/v1/cart/items",
                json={"product_id": "p1", "quantity": quantity},
            )
            assert response.status_code == 422, quantity

    @pytest.mark.asyncio
    async def test_mixed_currency_conflicts(self, client: TestClient, engine) -> None:
        await _prepare(
            engine, [("usd_item", "10.00", "USD"), ("eur_item", "8.00", "EUR")]
        )
        client.post(
            "/api/v1/cart/items", json={"product_id": "usd_item", "quantity": 1}
        )

        response = client.post(
            "/api/v1/cart/items", json={"product_id": "eur_item", "quantity": 1}
        )

        assert response.status_code == 409
        assert set(response.json()) == {"detail"}

    @pytest.mark.asyncio
    async def test_max_unique_lines_conflicts(self, client: TestClient, engine) -> None:
        await _seed_users(engine)
        await _seed_products(engine, [(f"p{i:03d}", "1.00") for i in range(101)])
        for i in range(100):
            response = client.post(
                "/api/v1/cart/items",
                json={"product_id": f"p{i:03d}", "quantity": 1},
            )
            assert response.status_code == 200, response.text

        response = client.post(
            "/api/v1/cart/items", json={"product_id": "p100", "quantity": 1}
        )

        assert response.status_code == 409
        assert set(response.json()) == {"detail"}

    @pytest.mark.asyncio
    async def test_increment_overflow_conflicts(
        self, client: TestClient, engine
    ) -> None:
        await _prepare(engine)
        client.post("/api/v1/cart/items", json={"product_id": "p1", "quantity": 10_000})

        response = client.post(
            "/api/v1/cart/items", json={"product_id": "p1", "quantity": 1}
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_subtotal_follows_catalog_price_changes(
        self, client: TestClient, auth, engine
    ) -> None:
        await _prepare(engine)
        client.post("/api/v1/cart/items", json={"product_id": "p1", "quantity": 2})

        auth["user"] = _user(OPERATOR, "operator")
        updated = client.patch("/api/v1/catalog/p1", json={"price": "60.00"})
        assert updated.status_code == 200, updated.text
        auth["user"] = _user(SHOPPER_A, "shopper")

        body = client.get("/api/v1/cart").json()
        assert body["subtotal"] == "120.00"
        assert body["items"][0]["unit_price"] == "60.00"


class TestInactiveProjection:
    @pytest.mark.asyncio
    async def test_deactivated_product_hidden_from_cart(
        self, client: TestClient, auth, engine
    ) -> None:
        await _prepare(engine)
        client.post("/api/v1/cart/items", json={"product_id": "p1", "quantity": 2})
        client.post("/api/v1/cart/items", json={"product_id": "p2", "quantity": 1})

        auth["user"] = _user(OPERATOR, "operator")
        deactivated = client.patch("/api/v1/catalog/p1", json={"active": False})
        assert deactivated.status_code == 200, deactivated.text
        auth["user"] = _user(SHOPPER_A, "shopper")

        body = client.get("/api/v1/cart").json()
        assert [i["product_id"] for i in body["items"]] == ["p2"]
        assert body["subtotal"] == "5.00"

        # The hidden line can no longer be grown or set …
        assert client.post(
            "/api/v1/cart/items", json={"product_id": "p1", "quantity": 1}
        ).json() == {"detail": "Product not found"}
        assert client.patch("/api/v1/cart/items/p1", json={"quantity": 1}).json() == {
            "detail": "Product not found"
        }
        # … but it stays removable through the idempotent path.
        removed = client.delete("/api/v1/cart/items/p1")
        assert removed.status_code == 200
        assert [i["product_id"] for i in removed.json()["items"]] == ["p2"]


class TestSetQuantity:
    @pytest.mark.asyncio
    async def test_set_replaces_quantity(self, client: TestClient, engine) -> None:
        await _prepare(engine)
        client.post("/api/v1/cart/items", json={"product_id": "p1", "quantity": 5})

        response = client.patch("/api/v1/cart/items/p1", json={"quantity": 2})

        assert response.status_code == 200
        assert response.json()["items"][0]["quantity"] == 2
        assert response.json()["subtotal"] == "99.98"

    @pytest.mark.asyncio
    async def test_set_missing_line_returns_404(
        self, client: TestClient, engine
    ) -> None:
        await _prepare(engine)

        response = client.patch("/api/v1/cart/items/p1", json={"quantity": 2})

        assert response.status_code == 404
        assert response.json() == {"detail": "Cart item not found"}

    @pytest.mark.asyncio
    async def test_set_scoped_to_owner(self, client: TestClient, auth, engine) -> None:
        await _prepare(engine)
        client.post("/api/v1/cart/items", json={"product_id": "p1", "quantity": 2})

        auth["user"] = _user(SHOPPER_B, "shopper")
        response = client.patch("/api/v1/cart/items/p1", json={"quantity": 1})

        assert response.status_code == 404
        assert response.json() == {"detail": "Cart item not found"}


class TestRemoveItem:
    @pytest.mark.asyncio
    async def test_remove_deletes_line(self, client: TestClient, engine) -> None:
        await _prepare(engine)
        client.post("/api/v1/cart/items", json={"product_id": "p1", "quantity": 1})
        client.post("/api/v1/cart/items", json={"product_id": "p2", "quantity": 1})

        response = client.delete("/api/v1/cart/items/p1")

        assert response.status_code == 200
        assert [i["product_id"] for i in response.json()["items"]] == ["p2"]

    @pytest.mark.asyncio
    async def test_remove_is_idempotent(self, client: TestClient, engine) -> None:
        await _prepare(engine)
        client.post("/api/v1/cart/items", json={"product_id": "p1", "quantity": 1})

        first = client.delete("/api/v1/cart/items/p1")
        second = client.delete("/api/v1/cart/items/p1")
        never = client.delete("/api/v1/cart/items/never-added")

        assert first.status_code == 200
        assert second.status_code == 200
        assert never.status_code == 200
        assert first.json()["items"] == []
        assert second.json()["cart_id"] == first.json()["cart_id"]
        assert never.json()["cart_id"] == first.json()["cart_id"]
