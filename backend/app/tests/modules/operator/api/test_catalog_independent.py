"""Independent operator-catalog probes (S1, S4, D1). Real JWTs, not get_current_user overrides."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.catalog.domain.entities import Product
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.iam.application.tokens import issue_token
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.shared.config import get_settings
from app.shared.db.session import get_db_session

WHEN = datetime(2024, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def client(engine, monkeypatch):
    monkeypatch.setenv(
        "EVENTCOMMERCE_JWT_SECRET", "verifier-secret-verifier-secret-verifier"
    )
    monkeypatch.setenv("EVENTCOMMERCE_JWT_ISSUER", "verifier")
    monkeypatch.setenv("EVENTCOMMERCE_JWT_AUDIENCE", "verifier")
    get_settings.cache_clear()
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    app = create_app()

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _token(role: str) -> dict[str, str]:
    raw = issue_token(uuid4(), f"{role}@example.com", role, settings=get_settings())
    return {"Authorization": f"Bearer {raw}"}


def _seed(engine) -> None:
    async def _go() -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            products = SqlAlchemyProductRepository(session)
            inventory = SqlAlchemyInventoryRepository(session)
            await products.save(
                Product(
                    id="aaa_inactive",
                    name="SECRET_INACTIVE_NAME",
                    description="SECRET_INACTIVE_DESC",
                    price=Decimal("19.99"),
                    currency="USD",
                    active=False,
                    created_at=WHEN,
                    updated_at=WHEN,
                )
            )
            await inventory.save(
                Inventory(
                    product_id="aaa_inactive",
                    available_quantity=4,
                    reserved_quantity=2,
                )
            )
            await products.save(
                Product(
                    id="mmm_active",
                    name="Visible",
                    description="public",
                    price=Decimal("10.00"),
                    currency="EUR",
                    active=True,
                    created_at=WHEN,
                    updated_at=WHEN,
                )
            )
            await inventory.save(
                Inventory(
                    product_id="mmm_active",
                    available_quantity=0,
                    reserved_quantity=0,
                )
            )
            await products.save(
                Product(
                    id="zzz_lonely",
                    name="SECRET_LONELY_NAME",
                    description=None,
                    price=Decimal("0.50"),
                    currency="USD",
                    active=True,
                    created_at=WHEN,
                    updated_at=WHEN,
                )
            )
            await session.commit()

    asyncio.run(_go())


async def _digest(engine) -> str:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        return (
            await session.execute(
                text(
                    "select md5(coalesce(string_agg(t, '|' order by t), '')) from ("
                    " select row(p.*)::text as t from catalog_products p"
                    " union all select row(i.*)::text from inventory i) s"
                )
            )
        ).scalar_one()


def test_empty_and_auth_no_leak(client: TestClient) -> None:
    # S4, D1
    op = _token("operator")
    assert client.get("/api/v1/operator/catalog", headers=op).json() == []
    anon = client.get("/api/v1/operator/catalog")
    assert anon.status_code == 401
    assert anon.json() == {"detail": "Not authenticated"}
    shop = _token("shopper")
    denied = client.get(
        "/api/v1/operator/catalog",
        headers={**shop, "X-Role": "operator"},
        params={"role": "operator", "include_inactive": "true"},
    )
    assert denied.status_code == 403
    assert denied.json() == {"detail": "Insufficient permissions"}
    assert "product_id" not in denied.text


def test_inactive_stock_null_order_and_public_unchanged(
    client: TestClient, engine
) -> None:
    # S1, D1
    _seed(engine)
    op = _token("operator")
    before = asyncio.run(_digest(engine))
    assert (
        client.get(
            "/api/v1/operator/catalog", headers=op, params={"limit": 0}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/operator/catalog", headers=op, params={"offset": -1}
        ).status_code
        == 422
    )
    assert asyncio.run(_digest(engine)) == before
    body = client.get("/api/v1/operator/catalog", headers=op)
    assert body.status_code == 200
    assert body.text == client.get("/api/v1/operator/catalog", headers=op).text
    rows = body.json()
    assert [row["product_id"] for row in rows] == [
        "aaa_inactive",
        "mmm_active",
        "zzz_lonely",
    ]
    assert rows[0]["active"] is False
    assert rows[0]["available_quantity"] == 4
    assert rows[0]["reserved_quantity"] == 2
    assert rows[0]["price"] == "19.99"
    assert rows[1]["available_quantity"] == 0
    assert rows[1]["reserved_quantity"] == 0
    assert rows[2]["available_quantity"] is None
    assert rows[2]["reserved_quantity"] is None
    assert rows[2]["price"] == "0.50"
    assert '"price":"10.00"' in body.text.replace(" ", "")
    past = client.get(
        "/api/v1/operator/catalog", headers=op, params={"limit": 10, "offset": 3}
    )
    assert past.status_code == 200
    assert past.json() == []
    public = client.get("/api/v1/catalog", params={"include_inactive": "true"})
    assert public.status_code == 200
    assert [row["id"] for row in public.json()] == ["mmm_active", "zzz_lonely"]
    assert client.get("/api/v1/catalog/aaa_inactive").status_code == 404
    assert asyncio.run(_digest(engine)) == before
