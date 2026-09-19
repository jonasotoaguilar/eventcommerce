"""Tests for the IAM user ORM model metadata."""

from sqlalchemy import (
    CheckConstraint,
    ColumnDefault,
    DateTime,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.modules.iam.infrastructure.models import UserModel


def _users_table() -> Table:
    table = UserModel.__table__
    assert isinstance(table, Table)
    return table


class TestUserModel:
    def test_tablename_is_users(self) -> None:
        assert UserModel.__tablename__ == "users"

    def test_id_is_uuid_primary_key_with_default(self) -> None:
        col = _users_table().c.id
        assert isinstance(col.type, PGUUID)
        assert col.primary_key
        assert not col.nullable
        default = col.default
        assert isinstance(default, ColumnDefault)
        assert callable(default.arg)
        assert getattr(default.arg, "__name__", "") == "uuid4"

    def test_email_and_password_hash_are_required_text(self) -> None:
        for name in ("email", "password_hash"):
            col = _users_table().c[name]
            assert isinstance(col.type, Text)
            assert not col.nullable

    def test_role_is_required_text_defaulting_to_shopper(self) -> None:
        col = _users_table().c.role
        assert isinstance(col.type, Text)
        assert not col.nullable
        default = col.default
        assert isinstance(default, ColumnDefault)
        assert default.arg == "shopper"

    def test_timestamps_are_tz_aware_and_required(self) -> None:
        for name in ("created_at", "updated_at"):
            col = _users_table().c[name]
            col_type = col.type
            assert isinstance(col_type, DateTime)
            assert col_type.timezone is True
            assert not col.nullable

    def test_updated_at_refreshes_on_update(self) -> None:
        col = _users_table().c.updated_at
        assert col.onupdate is not None

    def test_role_check_constraint_closes_shopper_operator(self) -> None:
        checks = [
            c for c in _users_table().constraints if isinstance(c, CheckConstraint)
        ]
        assert len(checks) == 1
        assert checks[0].name == "ck_users_role"
        assert str(checks[0].sqltext) == "role IN ('shopper', 'operator')"

    def test_single_case_insensitive_unique_email_index(self) -> None:
        unique_indexes = [i for i in _users_table().indexes if i.unique]
        assert len(unique_indexes) == 1
        index = unique_indexes[0]
        assert index.name == "ix_users_email_lower"
        rendered = " ".join(str(e) for e in index.expressions)
        assert "lower(" in rendered
        assert "email" in rendered

    def test_no_redundant_raw_email_uniqueness(self) -> None:
        assert not _users_table().c.email.unique
        for constraint in _users_table().constraints:
            if isinstance(constraint, UniqueConstraint):
                names = {c.name for c in constraint.columns}
                assert names != {"email"}
        for index in _users_table().indexes:
            if index.unique:
                assert index.name != "ix_users_email"
