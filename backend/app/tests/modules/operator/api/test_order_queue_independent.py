"""Independent operator-queue probes (S2, S8, D2). Real JWTs, not get_current_user overrides."""

import asyncio
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.app import create_app
from app.modules.iam.application.tokens import issue_token
from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.infrastructure.models import OrderModel
from app.modules.orders.infrastructure.sqlalchemy_repository import (
    SqlAlchemyOrderRepository,
)
from app.modules.payments.domain.entities import Payment
from app.modules.payments.infrastructure.sqlalchemy_repository import (
    SqlAlchemyPaymentRepository,
)
from app.shared.config import get_settings
from app.shared.db.session import get_db_session

LOW = UUID("00000000-0000-0000-0000-00000000000a")
HIGH = UUID("ffffffff-ffff-ffff-ffff-fffffffffffa")
LATER = UUID("00000000-0000-0000-0000-00000000000b")
WHEN = datetime(2024, 5, 2, 12, 0, 0)
AFTER = datetime(2024, 5, 2, 13, 0, 0)


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


def _seed_order(
    engine, order_id: UUID, *, status: str, created_at: datetime, items: list[OrderItem]
) -> None:
    async def _go() -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            await SqlAlchemyOrderRepository(session).save(
                Order(
                    id=order_id,
                    customer_id="cus",
                    status="pending",
                    cancel_reason=None,
                    created_at=created_at,
                    updated_at=created_at,
                    items=items,
                )
            )
            orm = (
                await session.execute(
                    select(OrderModel).where(OrderModel.id == order_id)
                )
            ).scalar_one()
            orm.status = status
            orm.created_at = created_at
            await session.commit()

    asyncio.run(_go())


def _seed_payment(
    engine,
    order_id: UUID,
    payment_id: UUID,
    amount: str,
    created_at: datetime,
    currency: str = "USD",
) -> None:
    async def _go() -> None:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with factory() as session:
            await SqlAlchemyPaymentRepository(session).save(
                Payment(
                    id=payment_id,
                    order_id=order_id,
                    status="failed",
                    amount=Decimal(amount),
                    currency=currency,
                    created_at=created_at,
                    failure_reason="hidden",
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
                    " select row(o.*)::text as t from orders o"
                    " union all select row(i.*)::text from order_items i"
                    " union all select row(p.*)::text from payments p) s"
                )
            )
        ).scalar_one()


def test_auth_matrix_and_no_shopper_bypass(client: TestClient) -> None:
    # S8
    assert client.get("/api/v1/operator/orders").json() == {
        "detail": "Not authenticated"
    }
    assert client.get("/api/v1/operator/orders").status_code == 401
    assert (
        client.get("/api/v1/operator/orders", params={"status": "shipped"}).status_code
        == 401
    )
    shop = _token("shopper")
    assert client.get("/api/v1/operator/orders", headers=shop).status_code == 403
    assert client.get("/api/v1/operator/orders", headers=shop).json() == {
        "detail": "Insufficient permissions"
    }
    leaked = client.get(
        "/api/v1/operator/orders",
        headers={**shop, "X-Role": "operator"},
        params={"role": "operator", "status": "confirmed", "limit": 200},
    )
    assert leaked.status_code == 403
    assert "order_id" not in leaked.text
    assert (
        client.get("/api/v1/operator/orders", headers=_token("operator")).json() == []
    )


def test_filters_bounds_tiebreak_and_stable_hash(client: TestClient, engine) -> None:
    # S2, D2
    pending = uuid4()
    confirmed = uuid4()
    other = uuid4()
    _seed_order(
        engine,
        pending,
        status="pending",
        created_at=datetime(2024, 5, 1, 12, 0, 0),
        items=[OrderItem(product_id=f"p{i}", quantity=2) for i in range(30)],
    )
    _seed_order(
        engine,
        confirmed,
        status="confirmed",
        created_at=WHEN,
        items=[OrderItem(product_id="p", quantity=1)],
    )
    _seed_order(
        engine,
        other,
        status="confirmed",
        created_at=datetime(2024, 5, 3, 12, 0, 0),
        items=[OrderItem(product_id="p", quantity=1)],
    )
    _seed_payment(engine, confirmed, LOW, "1.00", WHEN)
    _seed_payment(engine, confirmed, HIGH, "2.50", WHEN)
    _seed_payment(engine, other, uuid4(), "99.00", WHEN, currency="JPY")
    op = _token("operator")
    before = asyncio.run(_digest(engine))
    rejected = client.get(
        "/api/v1/operator/orders", headers=op, params={"status": "shipped"}
    )
    assert rejected.status_code == 422
    assert (
        client.get(
            "/api/v1/operator/orders", headers=op, params={"created_from": "not-a-date"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/operator/orders", headers=op, params={"limit": 0}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/operator/orders", headers=op, params={"limit": 201}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/v1/operator/orders", headers=op, params={"offset": -1}
        ).status_code
        == 422
    )
    rows = client.get("/api/v1/operator/orders", headers=op).json()
    by_id = {row["order_id"]: row for row in rows}
    assert by_id[str(pending)]["item_count"] == 60
    assert by_id[str(pending)]["total"] is None
    assert by_id[str(pending)]["currency"] is None
    assert by_id[str(confirmed)]["total"] == "2.50"
    assert by_id[str(other)]["total"] == "99.00"
    assert by_id[str(other)]["currency"] == "JPY"
    assert "hidden" not in client.get("/api/v1/operator/orders", headers=op).text
    window = client.get(
        "/api/v1/operator/orders",
        headers=op,
        params={
            "status": "confirmed",
            "created_from": "2024-05-02T00:00:00",
            "created_to": "2024-05-03T00:00:00",
        },
    )
    assert [row["order_id"] for row in window.json()] == [str(confirmed)]
    assert (
        client.get("/api/v1/operator/orders", headers=op, params={"offset": 50}).json()
        == []
    )
    _seed_payment(engine, confirmed, LATER, "3.25", AFTER)
    rerun = client.get(
        "/api/v1/operator/orders",
        headers=op,
        params={
            "status": "confirmed",
            "created_from": "2024-05-02T00:00:00",
            "created_to": "2024-05-03T00:00:00",
        },
    )
    assert rerun.json()[0]["total"] == "3.25"
    assert asyncio.run(_digest(engine)) != before
    mid = asyncio.run(_digest(engine))
    client.get("/api/v1/operator/orders", headers=op)
    client.get("/api/v1/operator/orders", headers=_token("shopper"))
    assert asyncio.run(_digest(engine)) == mid
