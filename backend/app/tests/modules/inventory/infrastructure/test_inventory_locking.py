"""RED tests for S3a: deadlock-safe FOR UPDATE inventory locking.

Slice 3 tasks 3.1/3.2 (RED): `lock_and_check_availability` locks inventory
rows `FOR UPDATE` in sorted `product_id` order so concurrent multi-line
reservations never deadlock and never lose updates; insufficient stock must
raise without leaving a partial reservation; a later persistence error must
roll back the original reservation. Task 3.3 pins the `ReleaseInventory`
compensation semantics against the locked flow.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.inventory.application.release_inventory import ReleaseInventory
from app.modules.inventory.domain.entities import Inventory
from app.modules.inventory.domain.errors import InsufficientStockError
from app.modules.inventory.domain.services import reserve_stock
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)


@pytest_asyncio.fixture
async def session_factory(
    engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(bind=engine, expire_on_commit=False)


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    products: dict[str, tuple[int, int]],
) -> None:
    async with session_factory() as session:
        async with session.begin():
            repo = SqlAlchemyInventoryRepository(session)
            for product_id, (available, reserved) in products.items():
                await repo.save(
                    Inventory(
                        product_id=product_id,
                        available_quantity=available,
                        reserved_quantity=reserved,
                    )
                )


async def _lock_and_reserve(
    repo: SqlAlchemyInventoryRepository, lines: list[tuple[str, int]]
) -> None:
    """The caller flow the checkout orchestrator will reuse: lock all lines,
    then reserve every locked row under the held locks."""
    locked = await repo.lock_and_check_availability(lines)
    quantities = dict(lines)
    for inventory in locked:
        reserve_stock(inventory, quantities[inventory.product_id])
        await repo.save(inventory)


class TestLockAndCheckAvailability:
    @pytest.mark.asyncio
    async def test_locks_checks_and_returns_sorted_inventory(
        self, session_factory
    ) -> None:
        await _seed(session_factory, {"p2": (10, 0), "p1": (5, 0)})
        async with session_factory() as session:
            async with session.begin():
                repo = SqlAlchemyInventoryRepository(session)
                locked = await repo.lock_and_check_availability([("p2", 2), ("p1", 1)])
                assert [inv.product_id for inv in locked] == ["p1", "p2"]
                await _lock_and_reserve(repo, [("p2", 2), ("p1", 1)])

        async with session_factory() as session:
            repo = SqlAlchemyInventoryRepository(session)
            p1 = await repo.get_by_product("p1")
            p2 = await repo.get_by_product("p2")
            assert p1 is not None
            assert p1.available_quantity == 4
            assert p1.reserved_quantity == 1
            assert p2 is not None
            assert p2.available_quantity == 8
            assert p2.reserved_quantity == 2

    @pytest.mark.asyncio
    async def test_insufficient_stock_raises_without_partial_reservation(
        self, session_factory
    ) -> None:
        await _seed(session_factory, {"p1": (5, 0), "p2": (0, 0)})
        async with session_factory() as session:
            async with session.begin():
                repo = SqlAlchemyInventoryRepository(session)
                with pytest.raises(InsufficientStockError):
                    await repo.lock_and_check_availability([("p1", 3), ("p2", 1)])

        async with session_factory() as session:
            repo = SqlAlchemyInventoryRepository(session)
            p1 = await repo.get_by_product("p1")
            p2 = await repo.get_by_product("p2")
            assert p1 is not None
            assert p1.available_quantity == 5
            assert p1.reserved_quantity == 0
            assert p2 is not None
            assert p2.available_quantity == 0
            assert p2.reserved_quantity == 0

    @pytest.mark.asyncio
    async def test_missing_product_raises(self, session_factory) -> None:
        await _seed(session_factory, {"p1": (5, 0)})
        async with session_factory() as session:
            async with session.begin():
                repo = SqlAlchemyInventoryRepository(session)
                with pytest.raises(InsufficientStockError):
                    await repo.lock_and_check_availability([("p1", 1), ("ghost", 1)])

    @pytest.mark.asyncio
    async def test_empty_items_returns_empty_list(self, session_factory) -> None:
        async with session_factory() as session:
            repo = SqlAlchemyInventoryRepository(session)
            assert await repo.lock_and_check_availability([]) == []

    @pytest.mark.asyncio
    async def test_rollback_after_later_persistence_error_undoes_reservation(
        self, session_factory
    ) -> None:
        await _seed(session_factory, {"p1": (10, 0)})
        session = session_factory()
        with pytest.raises(IntegrityError):
            async with session.begin():
                repo = SqlAlchemyInventoryRepository(session)
                await _lock_and_reserve(repo, [("p1", 3)])
                await session.execute(
                    text(
                        "INSERT INTO inventory (product_id, available_quantity, "
                        "reserved_quantity) VALUES ('p1', 99, 0)"
                    )
                )

        async with session_factory() as session2:
            repo2 = SqlAlchemyInventoryRepository(session2)
            p1 = await repo2.get_by_product("p1")
            assert p1 is not None
            assert p1.available_quantity == 10
            assert p1.reserved_quantity == 0

    @pytest.mark.asyncio
    async def test_release_inventory_compensates_after_locked_reservation(
        self, session_factory
    ) -> None:
        await _seed(session_factory, {"p1": (10, 0)})
        async with session_factory() as session:
            async with session.begin():
                repo = SqlAlchemyInventoryRepository(session)
                await _lock_and_reserve(repo, [("p1", 3)])
                await ReleaseInventory(repo).execute("p1", 3)

        async with session_factory() as session:
            repo = SqlAlchemyInventoryRepository(session)
            p1 = await repo.get_by_product("p1")
            assert p1 is not None
            assert p1.available_quantity == 10
            assert p1.reserved_quantity == 0


class TestConcurrentLocking:
    @pytest.mark.asyncio
    async def test_sorted_locking_is_deadlock_free_under_concurrent_multi_line_reserves(
        self, session_factory
    ) -> None:
        """Reversed-order multi-line reserves serialize instead of deadlocking.

        tx2's lines are input as [b, a] and tx1's as [a, b]. Sorted locking
        makes both acquire "a" first, so tx2 blocks on "a" holding nothing and
        tx1 proceeds to "b" and commits; tx2 then resumes and both reservations
        are applied. An input-order implementation makes tx2 hold "b" while
        waiting on "a" and tx1 wait on "b" — a circular wait PostgreSQL detects.
        """
        await _seed(session_factory, {"a": (10, 0), "b": (10, 0)})

        s1 = session_factory()
        async with s1.begin():
            repo1 = SqlAlchemyInventoryRepository(s1)
            await repo1.lock_and_check_availability([("a", 1)])

            s2 = session_factory()
            started = asyncio.Event()

            async def tx2() -> None:
                async with s2.begin():
                    started.set()
                    repo2 = SqlAlchemyInventoryRepository(s2)
                    locked = await repo2.lock_and_check_availability(
                        [("b", 1), ("a", 1)]
                    )
                    for inventory in locked:
                        reserve_stock(inventory, 1)
                        await repo2.save(inventory)

            task = asyncio.create_task(tx2())
            await started.wait()
            # tx2 must block on a row lock held by tx1.
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.5)

            # tx1 completes its own multi-line reserve (sorted order, no wait)
            # and commits; tx2's blocked statement then resumes.
            locked_ab = await asyncio.wait_for(
                repo1.lock_and_check_availability([("a", 1), ("b", 1)]),
                timeout=2.0,
            )
            for inventory in locked_ab:
                reserve_stock(inventory, 1)
                await repo1.save(inventory)

        await task

        async with session_factory() as session:
            repo = SqlAlchemyInventoryRepository(session)
            a = await repo.get_by_product("a")
            b = await repo.get_by_product("b")
            assert a is not None and b is not None
            assert a.available_quantity == 8
            assert a.reserved_quantity == 2
            assert b.available_quantity == 8
            assert b.reserved_quantity == 2

    @pytest.mark.asyncio
    async def test_concurrent_multi_line_reserves_do_not_lose_updates(
        self, session_factory
    ) -> None:
        await _seed(
            session_factory,
            {"p1": (10, 0), "p2": (10, 0), "p3": (10, 0)},
        )
        barrier = asyncio.Barrier(2)

        async def flow(lines: list[tuple[str, int]]) -> None:
            async with session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyInventoryRepository(session)
                    await barrier.wait()
                    await _lock_and_reserve(repo, lines)

        await asyncio.gather(
            flow([("p1", 1), ("p2", 1), ("p3", 1)]),
            flow([("p3", 1), ("p2", 1), ("p1", 1)]),
        )

        async with session_factory() as session:
            repo = SqlAlchemyInventoryRepository(session)
            for product_id in ("p1", "p2", "p3"):
                inventory = await repo.get_by_product(product_id)
                assert inventory is not None
                assert inventory.available_quantity == 8
                assert inventory.reserved_quantity == 2
