"""Tests for the refresh-tokens Alembic migration.

Loads the migration module directly and runs its upgrade and downgrade
against a recording ``op`` double, following the pattern in
``test_users_migration.py``, so the schema contract is verified without
a live database.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import DateTime, Text


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "alembic.ini").exists():
            return parent
    raise RuntimeError("Could not locate backend repo root with alembic.ini")


def _migration_path() -> Path:
    candidates = sorted(
        (_repo_root() / "alembic" / "versions").glob("*refresh*token*.py")
    )
    assert len(candidates) == 1, f"expected one refresh migration, found {candidates}"
    return candidates[0]


def _load_migration() -> Any:
    path = _migration_path()
    spec = importlib.util.spec_from_file_location("refresh_tokens_migration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load migration at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeOp:
    """Record Alembic op calls for upgrade/downgrade assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def create_table(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("create_table", args, kwargs))

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("create_index", args, kwargs))

    def drop_index(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("drop_index", args, kwargs))

    def drop_table(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("drop_table", args, kwargs))


def _upgrade_calls() -> list[tuple[str, tuple, dict]]:
    migration = _load_migration()
    fake = _FakeOp()
    migration.op = fake
    migration.upgrade()
    return fake.calls


def _downgrade_calls() -> list[tuple[str, tuple, dict]]:
    migration = _load_migration()
    fake = _FakeOp()
    migration.op = fake
    migration.downgrade()
    return fake.calls


class TestRefreshTokensMigration:
    def test_migration_chains_from_order_lifecycle_head(self) -> None:
        migration = _load_migration()

        assert migration.down_revision == "f4a5b6c7d8e9"

    def test_upgrade_creates_table_then_family_index(self) -> None:
        kinds = [c[0] for c in _upgrade_calls()]

        assert kinds == ["create_table", "create_index"]

    def test_upgrade_creates_refresh_tokens_table_with_contract(self) -> None:
        calls = _upgrade_calls()
        tables = [c for c in calls if c[0] == "create_table"]
        assert len(tables) == 1
        args = tables[0][1]

        assert args[0] == "refresh_tokens"
        by_name = {c.name: c for c in args[1:] if isinstance(c, sa.Column)}
        assert set(by_name) == {
            "id",
            "user_id",
            "family_id",
            "token_hash",
            "created_at",
            "expires_at",
            "consumed_at",
            "revoked_at",
        }

        assert isinstance(by_name["id"].type, sa.dialects.postgresql.UUID)
        assert not by_name["id"].nullable
        assert isinstance(by_name["user_id"].type, sa.dialects.postgresql.UUID)
        assert not by_name["user_id"].nullable
        assert isinstance(by_name["family_id"].type, sa.dialects.postgresql.UUID)
        assert not by_name["family_id"].nullable
        assert isinstance(by_name["token_hash"].type, Text)
        assert not by_name["token_hash"].nullable
        for name in ("created_at", "expires_at"):
            col_type = by_name[name].type
            assert isinstance(col_type, DateTime)
            assert col_type.timezone is True
            assert not by_name[name].nullable
        for name in ("consumed_at", "revoked_at"):
            col_type = by_name[name].type
            assert isinstance(col_type, DateTime)
            assert col_type.timezone is True
            assert by_name[name].nullable

        metadata = sa.MetaData()
        sa.Table(
            "users",
            metadata,
            sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        )
        resolved = sa.Table("refresh_tokens", metadata, *args[1:])
        uniques = [
            c for c in resolved.constraints if isinstance(c, sa.UniqueConstraint)
        ]
        assert any(
            {col.name for col in u.columns} == {"token_hash"} for u in uniques
        ), "token_hash must be unique"
        fks = list(resolved.foreign_key_constraints)
        assert len(fks) == 1
        assert [c.name for c in fks[0].columns] == ["user_id"]
        assert [e.column.table.name for e in fks[0].elements] == ["users"]
        assert fks[0].ondelete == "CASCADE"
        pks = [c for c in args[1:] if isinstance(c, sa.PrimaryKeyConstraint)]
        assert len(pks) == 1

    def test_upgrade_indexes_family_id(self) -> None:
        calls = _upgrade_calls()
        index_calls = [c for c in calls if c[0] == "create_index"]

        assert len(index_calls) == 1
        _, args, kwargs = index_calls[0]
        assert args[0] == "ix_refresh_tokens_family_id"
        assert args[1] == "refresh_tokens"
        assert kwargs.get("unique", False) is False
        columns = args[2] if isinstance(args[2], list) else args[2:]
        assert [str(c) for c in columns] == ["family_id"]

    def test_downgrade_drops_index_then_table(self) -> None:
        calls = _downgrade_calls()

        kinds = [c[0] for c in calls]
        assert kinds == ["drop_index", "drop_table"]
        _, drop_index_args, drop_index_kwargs = calls[0]
        assert drop_index_args[0] == "ix_refresh_tokens_family_id"
        assert drop_index_kwargs.get("table_name") == "refresh_tokens"
        _, drop_table_args, _ = calls[1]
        assert drop_table_args[0] == "refresh_tokens"
