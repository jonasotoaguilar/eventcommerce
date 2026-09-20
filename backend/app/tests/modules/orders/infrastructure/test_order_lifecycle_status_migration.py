"""Tests for the order lifecycle status CHECK constraint migration (U1)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect


MIGRATION_PATH = (
    Path(__file__).resolve().parents[5]
    / "alembic"
    / "versions"
    / "f4a5b6c7d8e9_order_lifecycle_status.py"
)

CONSTRAINT_NAME = "ck_orders_status_lifecycle"
EXPECTED_STATUSES = (
    "pending",
    "inventory_reserved",
    "payment_authorized",
    "confirmed",
    "cancelled",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "order_lifecycle_status_migration", MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load migration at {MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_names(sync_connection) -> dict[str, str]:
    return {
        check["name"]: check["sqltext"]
        for check in inspect(sync_connection).get_check_constraints("orders")
    }


class TestOrderLifecycleStatusMigration:
    def test_migration_chains_after_current_head(self) -> None:
        migration = _load_migration()

        assert migration.revision == "f4a5b6c7d8e9"
        # NOTE: U1 was scoped as chained after cart head e3f4a5b6c7d8, but
        # that revision is not an ancestor of this branch (it lives on
        # origin/feat/catalog-cart). Chaining after the actual branch head
        # keeps `alembic upgrade head` linear; rechain to e3f4a5b6c7d8
        # when catalog-cart merges underneath this branch.
        assert migration.down_revision == "c1d2e3f4a5b6"

    @pytest.mark.asyncio
    async def test_downgrade_removes_and_upgrade_restores_constraint(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        migration = _load_migration()
        connection = await db_session.connection()

        def apply_migration(sync_connection) -> tuple[dict, dict, dict]:
            operations = Operations(MigrationContext.configure(sync_connection))
            monkeypatch.setattr(migration, "op", operations, raising=False)
            before = _check_names(sync_connection)
            migration.downgrade()
            downgraded = _check_names(sync_connection)
            migration.upgrade()
            upgraded = _check_names(sync_connection)
            return before, downgraded, upgraded

        before, downgraded, upgraded = await connection.run_sync(apply_migration)

        # Model metadata (create_all) already carries the mirrored constraint.
        assert CONSTRAINT_NAME in before
        assert all(name != CONSTRAINT_NAME for name in downgraded)
        assert CONSTRAINT_NAME in upgraded
        for status in EXPECTED_STATUSES:
            assert status in str(upgraded[CONSTRAINT_NAME])
