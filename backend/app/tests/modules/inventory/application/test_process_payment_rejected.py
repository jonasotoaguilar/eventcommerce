"""Tests for inventory-side PaymentRejected compensation (U3)."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.modules.inventory.application.process_payment_rejected import (
    CONSUMER_NAME,
    ProcessPaymentRejected,
)
from app.modules.inventory.domain.entities import Inventory
from app.modules.orders.domain.entities import Order, OrderItem
from app.modules.orders.domain.errors import OrderNotFoundError


class FakeInventoryRepository:
    def __init__(self, rows: dict[str, Inventory] | None = None) -> None:
        self._rows = dict(rows or {})
        self.save_calls = 0

    async def get_by_product(self, product_id: str) -> Inventory | None:
        row = self._rows.get(product_id)
        if row is None:
            return None
        return Inventory(row.product_id, row.available_quantity, row.reserved_quantity)

    async def save(self, inventory: Inventory) -> None:
        self.save_calls += 1
        self._rows[inventory.product_id] = Inventory(
            inventory.product_id,
            inventory.available_quantity,
            inventory.reserved_quantity,
        )


class FakeOrderRepository:
    """Read-only order store: save raises so order mutation is impossible."""

    def __init__(self, orders: dict[UUID, Order]) -> None:
        self._orders = dict(orders)

    async def get_by_id(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

    async def save(self, order: Order) -> None:  # pragma: no cover
        raise AssertionError("inventory must never save orders")


class FakeIdempotency:
    def __init__(self) -> None:
        self._processed: set[tuple[str, str]] = set()

    async def is_processed(self, eid: str, cname: str) -> bool:
        return (eid, cname) in self._processed

    async def mark_processed(self, eid: str, cname: str) -> None:
        self._processed.add((eid, cname))


def _order(oid: UUID, status: str, items: list[OrderItem] | None = None) -> Order:
    now = datetime.now(timezone.utc)
    return Order(
        id=oid,
        customer_id="cus_1",
        status=status,
        cancel_reason=None,
        created_at=now,
        updated_at=now,
        items=items if items is not None else [OrderItem(product_id="p1", quantity=2)],
    )


def _harness(order: Order | None, rows: dict[str, Inventory] | None = None):  # type: ignore[no-untyped-def]
    inv_repo = FakeInventoryRepository(rows)
    order_repo = FakeOrderRepository({order.id: order} if order else {})
    idem = FakeIdempotency()
    uc = ProcessPaymentRejected(inv_repo, order_repo, idem)  # type: ignore[arg-type]
    return uc, inv_repo, order_repo, idem


class TestProcessPaymentRejected:
    @pytest.mark.asyncio
    async def test_releases_reserved_quantities_exactly_once(self) -> None:
        oid = uuid4()
        order = _order(
            oid,
            "inventory_reserved",
            [
                OrderItem(product_id="p1", quantity=2),
                OrderItem(product_id="p2", quantity=1),
            ],
        )
        uc, inv_repo, _, idem = _harness(
            order,
            {"p1": Inventory("p1", 8, 2), "p2": Inventory("p2", 4, 1)},
        )
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid)

        p1 = await inv_repo.get_by_product("p1")
        p2 = await inv_repo.get_by_product("p2")
        assert p1 is not None and (p1.available_quantity, p1.reserved_quantity) == (
            10,
            0,
        )
        assert p2 is not None and (p2.available_quantity, p2.reserved_quantity) == (
            5,
            0,
        )
        assert inv_repo.save_calls == 2
        assert await idem.is_processed(eid, CONSUMER_NAME)

        # Duplicate delivery never double-releases.
        await uc.execute(event_id=eid, order_id=oid)
        p1 = await inv_repo.get_by_product("p1")
        assert p1 is not None and (p1.available_quantity, p1.reserved_quantity) == (
            10,
            0,
        )
        assert inv_repo.save_calls == 2

    @pytest.mark.asyncio
    async def test_releases_while_staged_before_orders_cancel(self) -> None:
        oid = uuid4()
        uc, inv_repo, _, _ = _harness(
            _order(oid, "inventory_reserved"),
            {"p1": Inventory("p1", 8, 2)},
        )
        await uc.execute(event_id=str(uuid4()), order_id=oid)
        inv = await inv_repo.get_by_product("p1")
        assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (
            10,
            0,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status", ["pending", "payment_authorized", "confirmed", "cancelled"]
    )
    async def test_non_reserved_statuses_are_claimed_without_release(
        self, status: str
    ) -> None:
        oid = uuid4()
        uc, inv_repo, _, idem = _harness(
            _order(oid, status),
            {"p1": Inventory("p1", 8, 2)},
        )
        eid = str(uuid4())
        await uc.execute(event_id=eid, order_id=oid)
        inv = await inv_repo.get_by_product("p1")
        assert inv is not None and (inv.available_quantity, inv.reserved_quantity) == (
            8,
            2,
        )
        assert inv_repo.save_calls == 0
        assert await idem.is_processed(eid, CONSUMER_NAME)

    @pytest.mark.asyncio
    async def test_missing_inventory_row_is_skipped(self) -> None:
        oid = uuid4()
        uc, inv_repo, _, _ = _harness(_order(oid, "inventory_reserved"), {})
        await uc.execute(event_id=str(uuid4()), order_id=oid)
        assert inv_repo.save_calls == 0

    @pytest.mark.asyncio
    async def test_order_status_never_mutated(self) -> None:
        oid = uuid4()
        order = _order(oid, "inventory_reserved")
        uc, _, _, _ = _harness(order, {"p1": Inventory("p1", 8, 2)})
        await uc.execute(event_id=str(uuid4()), order_id=oid)
        assert order.status == "inventory_reserved"
        assert not hasattr(uc, "_outbox")

    @pytest.mark.asyncio
    async def test_missing_order_raises_and_not_marked(self) -> None:
        uc, _, _, idem = _harness(None, {})
        oid, eid = uuid4(), str(uuid4())
        with pytest.raises(OrderNotFoundError):
            await uc.execute(event_id=eid, order_id=oid)
        assert not await idem.is_processed(eid, CONSUMER_NAME)
