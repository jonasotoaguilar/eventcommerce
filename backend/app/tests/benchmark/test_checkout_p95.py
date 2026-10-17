"""p95 checkout latency benchmark for the deterministic MVP path (S6/U9).

Helper tests below always run. The benchmark itself only runs with
``EVENTCOMMERCE_BENCHMARK=1`` so the default suite stays fast.
"""

from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.app import create_app
from app.modules.cart.infrastructure.models import CartItemModel, CartModel  # noqa: F401
from app.modules.catalog.infrastructure.models import ProductModel  # noqa: F401
from app.modules.iam.infrastructure.models import UserModel  # noqa: F401
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)
from app.modules.payments.domain.policy import APPROVAL_THRESHOLD
from app.shared.config import get_settings
from app.shared.db.session import get_db_session

assert CartModel is not None
assert CartItemModel is not None
assert ProductModel is not None
assert UserModel is not None

BENCHMARK_ENV_VAR = "EVENTCOMMERCE_BENCHMARK"
BENCHMARK_ENABLED = os.environ.get(BENCHMARK_ENV_VAR) == "1"
SAMPLE_SIZE = 50
MIN_CONFIRMED_SAMPLES = 20
P95_BUDGET_MS = 500.0
CHECKOUT_URL = "/api/v1/checkout"
BENCHMARK_COMMAND = (
    "EVENTCOMMERCE_POSTGRES_DB=eventcommerce_bench "
    "EVENTCOMMERCE_BENCHMARK=1 uv run pytest "
    "app/tests/benchmark/test_checkout_p95.py -q -s"
)
PRODUCT_ID = "BENCH-1"
BENCH_PASSWORD = "bench-pass-1"


def percentile(samples: list[float], pct: float) -> float:
    if not samples:
        raise ValueError("percentile requires at least one sample")
    if not 0.0 <= pct <= 100.0:
        raise ValueError(f"pct must be within 0..100, got {pct}")
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct / 100.0 * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return ordered[low]
    fraction = rank - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def summarize(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        raise ValueError("summarize requires at least one sample")
    return {
        "count": len(samples),
        "min": min(samples),
        "p50": percentile(samples, 50),
        "p95": percentile(samples, 95),
        "p99": percentile(samples, 99),
        "max": max(samples),
    }


def format_report(
    summary: dict[str, float | int], *, budget_ms: float, command: str, label: str = ""
) -> str:
    verdict = "PASS" if summary["p95"] < budget_ms else "FAIL"
    return (
        f"checkout p95 benchmark\ncommand: {command}\nscope: {label}\n"
        if label
        else f"checkout p95 benchmark\ncommand: {command}\n"
    ) + (
        f"samples: {summary['count']}\n"
        f"min: {summary['min']:.2f} ms\n"
        f"p50: {summary['p50']:.2f} ms\n"
        f"p95: {summary['p95']:.2f} ms\n"
        f"p99: {summary['p99']:.2f} ms\n"
        f"max: {summary['max']:.2f} ms\n"
        f"budget: p95 < {budget_ms:.2f} ms\n"
        f"verdict: {verdict}"
    )


class TestPercentile:
    def test_p50_of_even_sample_interpolates(self) -> None:
        assert percentile([10.0, 20.0, 30.0, 40.0], 50) == 25.0

    def test_edges_return_min_and_max_regardless_of_order(self) -> None:
        assert percentile([5.0, 1.0, 9.0], 0) == 1.0
        assert percentile([5.0, 1.0, 9.0], 100) == 9.0

    def test_single_sample_returns_that_sample(self) -> None:
        assert percentile([7.0], 95) == 7.0

    def test_empty_sample_raises(self) -> None:
        with pytest.raises(ValueError):
            percentile([], 95)

    @pytest.mark.parametrize("pct", [-1.0, 100.5])
    def test_out_of_range_pct_raises(self, pct: float) -> None:
        with pytest.raises(ValueError):
            percentile([1.0, 2.0], pct)


class TestSummarize:
    def test_reports_count_extremes_and_percentiles(self) -> None:
        summary = summarize([2.0, 4.0, 6.0, 8.0])

        assert summary["count"] == 4
        assert summary["min"] == 2.0
        assert summary["max"] == 8.0
        assert summary["p50"] == 5.0
        assert summary["p95"] == pytest.approx(percentile([2.0, 4.0, 6.0, 8.0], 95))
        assert summary["p99"] == pytest.approx(percentile([2.0, 4.0, 6.0, 8.0], 99))

    def test_empty_sample_raises(self) -> None:
        with pytest.raises(ValueError):
            summarize([])


class TestFormatReport:
    def test_includes_metrics_command_and_pass_verdict(self) -> None:
        summary = summarize([10.0, 20.0, 30.0])
        report = format_report(summary, budget_ms=500.0, command=BENCHMARK_COMMAND)

        assert f"samples: {summary['count']}" in report
        assert f"p50: {summary['p50']:.2f} ms" in report
        assert f"p95: {summary['p95']:.2f} ms" in report
        assert f"p99: {summary['p99']:.2f} ms" in report
        assert f"min: {summary['min']:.2f} ms" in report
        assert f"max: {summary['max']:.2f} ms" in report
        assert BENCHMARK_COMMAND in report
        assert "PASS" in report

    def test_over_budget_reports_fail(self) -> None:
        summary = summarize([600.0, 700.0])
        report = format_report(summary, budget_ms=500.0, command="cmd")

        assert "FAIL" in report

    def test_label_names_the_measured_scope(self) -> None:
        summary = summarize([10.0, 20.0])

        labelled = format_report(
            summary, budget_ms=500.0, command="cmd", label="confirmed only"
        )
        unlabelled = format_report(summary, budget_ms=500.0, command="cmd")

        assert "scope: confirmed only" in labelled
        assert "scope:" not in unlabelled


@pytest_asyncio.fixture
async def session_factory(
    engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def http_client(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    # Real register/login needs a JWT secret; the local .env leaves it
    # empty, so scope a benchmark-only secret like the operator probes do.
    monkeypatch.setenv(
        "EVENTCOMMERCE_JWT_SECRET", "benchmark-secret-not-for-production"
    )
    monkeypatch.setenv("EVENTCOMMERCE_JWT_ISSUER", "benchmark")
    monkeypatch.setenv("EVENTCOMMERCE_JWT_AUDIENCE", "benchmark")
    get_settings.cache_clear()
    try:
        app = create_app()

        async def override_get_session() -> AsyncIterator[AsyncSession]:
            async with session_factory() as session:
                yield session

        app.dependency_overrides[get_db_session] = override_get_session
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        get_settings.cache_clear()


async def _register_and_login(client: httpx.AsyncClient) -> dict[str, str]:
    email = f"bench-{uuid4().hex}@example.com"
    registered = await client.post(
        "/api/v1/iam/register",
        json={"email": email, "password": BENCH_PASSWORD},
    )
    assert registered.status_code == 201, registered.text
    logged_in = await client.post(
        "/api/v1/iam/login",
        json={"email": email, "password": BENCH_PASSWORD},
    )
    assert logged_in.status_code == 200, logged_in.text
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


async def _seed_benchmark_product(db_session: AsyncSession) -> None:
    db_session.add(
        ProductModel(
            id=PRODUCT_ID,
            name="Benchmark Widget",
            description=None,
            price=Decimal("10.00"),
            currency="USD",
            active=True,
        )
    )
    await db_session.flush()
    await SqlAlchemyInventoryRepository(db_session).save(
        Inventory(
            product_id=PRODUCT_ID,
            available_quantity=100000,
            reserved_quantity=0,
        )
    )
    await db_session.commit()


async def _reset_cart_to_single_line(
    client: httpx.AsyncClient, auth: dict[str, str]
) -> str:
    cart = await client.get("/api/v1/cart", headers=auth)
    assert cart.status_code == 200, cart.text
    for item in cart.json()["items"]:
        removed = await client.delete(
            f"/api/v1/cart/items/{item['product_id']}", headers=auth
        )
        assert removed.status_code == 200, removed.text
    added = await client.post(
        "/api/v1/cart/items",
        json={"product_id": PRODUCT_ID, "quantity": 1},
        headers=auth,
    )
    assert added.status_code == 200, added.text
    return str(added.json()["cart_id"])


@pytest.mark.skipif(
    not BENCHMARK_ENABLED,
    reason=f"Set {BENCHMARK_ENV_VAR}=1 to run the checkout latency benchmark",
)
@pytest.mark.asyncio
async def test_checkout_p95_under_budget(
    http_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    auth = await _register_and_login(http_client)
    await _seed_benchmark_product(db_session)

    attempts: list[tuple[float, str]] = []
    for _ in range(SAMPLE_SIZE):
        cart_id = await _reset_cart_to_single_line(http_client, auth)
        started = time.perf_counter()
        response = await http_client.post(
            CHECKOUT_URL,
            json={"cart_id": cart_id},
            headers={**auth, "Idempotency-Key": uuid4().hex},
        )
        attempts.append(((time.perf_counter() - started) * 1000.0, ""))
        assert response.status_code == 201, response.text
        attempts[-1] = (attempts[-1][0], str(response.json()["status"]))

    assert len(attempts) == SAMPLE_SIZE
    latencies = [latency for latency, _ in attempts]
    confirmed = [latency for latency, status in attempts if status == "confirmed"]
    cancelled = [latency for latency, status in attempts if status == "cancelled"]
    assert len(confirmed) + len(cancelled) == SAMPLE_SIZE
    assert len(confirmed) >= MIN_CONFIRMED_SAMPLES, (
        f"only {len(confirmed)} confirmed samples of {SAMPLE_SIZE}; the happy-path "
        "p95 needs a usable sample"
    )

    summary = summarize(latencies)
    confirmed_summary = summarize(confirmed)
    print(format_report(summary, budget_ms=P95_BUDGET_MS, command=BENCHMARK_COMMAND))
    print(
        format_report(
            confirmed_summary,
            budget_ms=P95_BUDGET_MS,
            command=BENCHMARK_COMMAND,
            label="confirmed only (payment approved)",
        )
    )
    if cancelled:
        print(
            format_report(
                summarize(cancelled),
                budget_ms=P95_BUDGET_MS,
                command=BENCHMARK_COMMAND,
                label="cancelled only (payment rejected)",
            )
        )
    print(
        f"outcomes: confirmed={len(confirmed)} cancelled={len(cancelled)} "
        f"(approval threshold {APPROVAL_THRESHOLD}/256)"
    )
    assert summary["p95"] < P95_BUDGET_MS, (
        f"p95 {summary['p95']:.2f} ms at or above {P95_BUDGET_MS:.2f} ms budget"
    )
    assert confirmed_summary["p95"] < P95_BUDGET_MS, (
        f"confirmed-only p95 {confirmed_summary['p95']:.2f} ms at or above "
        f"{P95_BUDGET_MS:.2f} ms budget"
    )
