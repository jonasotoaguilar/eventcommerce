"""Tests for the pending outbox polling index migration."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect


MIGRATION_PATH = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "9e0f1a2b3c4d_index_pending_outbox.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "pending_outbox_migration", MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load migration at {MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPendingOutboxMigration:
    def test_migration_is_additive_child_of_current_head(self) -> None:
        migration = _load_migration()

        assert migration.revision == "9e0f1a2b3c4d"
        assert migration.down_revision == "8d9e0f1a2b3c"

    @pytest.mark.asyncio
    async def test_upgrade_creates_composite_index_and_downgrade_removes_it(
        self, db_session
    ) -> None:
        migration = _load_migration()
        connection = await db_session.connection()

        def apply_migration(sync_connection) -> tuple[list[dict], list[dict]]:
            operations = Operations(MigrationContext.configure(sync_connection))
            migration.op = operations
            migration.upgrade()
            upgraded = inspect(sync_connection).get_indexes("outbox_events")
            migration.downgrade()
            downgraded = inspect(sync_connection).get_indexes("outbox_events")
            return upgraded, downgraded

        upgraded, downgraded = await connection.run_sync(apply_migration)

        assert {index["name"]: index["column_names"] for index in upgraded}[
            "ix_outbox_events_status_created_at"
        ] == ["status", "created_at"]
        assert all(
            index["name"] != "ix_outbox_events_status_created_at"
            for index in downgraded
        )
