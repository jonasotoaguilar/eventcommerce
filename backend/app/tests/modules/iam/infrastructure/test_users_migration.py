"""Tests for the IAM users Alembic migration.

These tests load the migration module directly and run its upgrade and
downgrade against a recording ``op`` double, so the schema contract is
verified without requiring a live database.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, Text


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "alembic.ini").exists():
            return parent
    raise RuntimeError("Could not locate backend repo root with alembic.ini")


MIGRATION_PATH = _repo_root() / "alembic" / "versions" / "c1d2e3f4a5b6_add_iam_users.py"


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("iam_users_migration", MIGRATION_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load migration at {MIGRATION_PATH}")
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


def _create_table_args(calls: list[tuple[str, tuple, dict]]) -> tuple:
    tables = [c for c in calls if c[0] == "create_table"]
    assert len(tables) == 1
    return tables[0][1]


class TestIamUsersMigration:
    def test_migration_chains_from_current_head(self) -> None:
        migration = _load_migration()

        assert migration.revision == "c1d2e3f4a5b6"
        assert migration.down_revision == "9e0f1a2b3c4d"

    def test_upgrade_runs_create_table_before_create_index(self) -> None:
        kinds = [c[0] for c in _upgrade_calls()]

        assert kinds == ["create_table", "create_index"]

    def test_upgrade_creates_users_table_with_contract(self) -> None:
        args = _create_table_args(_upgrade_calls())

        assert args[0] == "users"
        by_name = {c.name: c for c in args[1:] if isinstance(c, sa.Column)}
        assert set(by_name) == {
            "id",
            "email",
            "password_hash",
            "role",
            "created_at",
            "updated_at",
        }

        assert isinstance(by_name["id"].type, sa.dialects.postgresql.UUID)
        assert not by_name["id"].nullable
        for name in ("email", "password_hash"):
            assert isinstance(by_name[name].type, Text)
            assert not by_name[name].nullable
        assert isinstance(by_name["role"].type, Text)
        assert not by_name["role"].nullable
        server_default = by_name["role"].server_default
        assert isinstance(server_default, sa.DefaultClause)
        assert "shopper" in str(server_default.arg)
        for name in ("created_at", "updated_at"):
            col_type = by_name[name].type
            assert isinstance(col_type, DateTime)
            assert col_type.timezone is True
            assert not by_name[name].nullable

        checks = [c for c in args[1:] if isinstance(c, CheckConstraint)]
        assert len(checks) == 1
        assert checks[0].name == "ck_users_role"
        assert str(checks[0].sqltext) == "role IN ('shopper', 'operator')"

        pks = [c for c in args[1:] if isinstance(c, sa.PrimaryKeyConstraint)]
        assert len(pks) == 1
        resolved = sa.Table("users", sa.MetaData(), *args[1:])
        assert set(resolved.primary_key.columns.keys()) == {"id"}

    def test_upgrade_adds_single_unique_lower_email_index(self) -> None:
        calls = _upgrade_calls()
        index_calls = [c for c in calls if c[0] == "create_index"]

        unique_calls = [c for c in index_calls if c[2].get("unique") is True]
        assert len(unique_calls) == 1
        _, args, _ = unique_calls[0]
        assert args[0] == "ix_users_email_lower"
        assert args[1] == "users"
        expressions = args[2] if isinstance(args[2], list) else args[2:]
        rendered = " ".join(str(e.compile()) for e in expressions)
        assert "lower(" in rendered
        assert "email" in rendered

    def test_downgrade_drops_index_then_table(self) -> None:
        calls = _downgrade_calls()

        kinds = [c[0] for c in calls]
        assert kinds == ["drop_index", "drop_table"]
        _, drop_index_args, drop_index_kwargs = calls[0]
        assert drop_index_args[0] == "ix_users_email_lower"
        assert drop_index_kwargs.get("table_name") == "users"
        _, drop_table_args, _ = calls[1]
        assert drop_table_args[0] == "users"

    def test_alembic_env_registers_user_model_metadata(self) -> None:
        tree = ast.parse((_repo_root() / "alembic" / "env.py").read_text())
        user_model_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and "UserModel" in {alias.name for alias in node.names}
        }

        assert user_model_modules == {"app.modules.iam.infrastructure.models"}
