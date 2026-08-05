"""Tests for the extend_checkout_idempotency Alembic migration.

These tests run the actual migration upgrade and downgrade against a
disposable Postgres database so the schema contract is verified end-to-end.

Slice 1 task 1.1: failing tests that pin the new ``processed_events``
columns, the ``state`` check constraint, the legacy UUID backfill, the
``payments.amount`` NUMERIC(11,2) widening, and the symmetric downgrade.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url


REPO_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
ALEMBIC_DIR = REPO_ROOT / "alembic"


def _admin_url() -> str:
    from app.shared.config import get_settings

    s = get_settings()
    return (
        f"postgresql+psycopg://{s.postgres_user}:{s.postgres_password}"
        f"@{s.postgres_host}:{s.postgres_port}/postgres"
    )


def _admin_engine() -> Engine:
    return create_engine(_admin_url(), isolation_level="AUTOCOMMIT", future=True)


def _recreate_db(db_name: str) -> None:
    eng = _admin_engine()
    try:
        with eng.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        eng.dispose()


@pytest.fixture
def migration_engine() -> Iterator[Engine]:
    """Yield a sync engine whose database exists and is empty."""
    db_name = "evtcmrc_mig_checkout_s1"
    _recreate_db(db_name)
    engine = create_engine(make_url(_admin_url()).set(database=db_name), future=True)
    try:
        yield engine
    finally:
        engine.dispose()
        eng = _admin_engine()
        try:
            with eng.connect() as conn:
                conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        finally:
            eng.dispose()


def _run(cfg_args: list[str], engine: Engine, action: str, target: str) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        if action == "upgrade":
            command.upgrade(cfg, target)
        else:
            command.downgrade(cfg, target)


def _column_info(engine: Engine, table: str) -> dict[str, dict[str, object]]:
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT column_name, data_type, character_maximum_length, "
                    "       numeric_precision, numeric_scale, is_nullable "
                    "FROM information_schema.columns WHERE table_name = :table"
                ),
                {"table": table},
            )
            .mappings()
            .all()
        )
    return {r["column_name"]: dict(r) for r in rows}


class TestExtendCheckoutIdempotencyMigration:
    def test_upgrade_shape(self, migration_engine: Engine) -> None:
        _run([], migration_engine, "upgrade", "head")

        cols = _column_info(migration_engine, "processed_events")
        assert cols["event_id"]["data_type"] == "text"
        assert cols["event_id"]["is_nullable"] == "NO"
        assert cols["payload_hash"]["data_type"] == "character"
        assert cols["payload_hash"]["character_maximum_length"] == 64
        assert cols["payload_hash"]["is_nullable"] == "YES"
        assert cols["response_status"]["data_type"] == "integer"
        assert cols["response_status"]["is_nullable"] == "YES"
        assert cols["response_body"]["data_type"] == "json"
        assert cols["response_body"]["is_nullable"] == "YES"
        assert cols["updated_at"]["is_nullable"] == "NO"
        assert cols["state"]["data_type"] == "text"
        assert cols["state"]["is_nullable"] == "NO"

    def test_payments_amount_is_numeric_11_2(self, migration_engine: Engine) -> None:
        _run([], migration_engine, "upgrade", "head")
        cols = _column_info(migration_engine, "payments")
        assert cols["amount"]["data_type"] == "numeric"
        assert cols["amount"]["numeric_precision"] == 11
        assert cols["amount"]["numeric_scale"] == 2
        assert cols["amount"]["is_nullable"] == "NO"

    def test_legacy_uuid_rows_backfill_state_processed(
        self, migration_engine: Engine
    ) -> None:
        # Apply only the prior migrations to get the legacy UUID schema.
        _run([], migration_engine, "upgrade", "4d6e7a8b9c0f")
        with migration_engine.begin() as conn:
            for uuid in (
                "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222",
            ):
                conn.execute(
                    text(
                        "INSERT INTO processed_events "
                        "(event_id, consumer_name, processed_at) "
                        "VALUES (:e, 'legacy', NOW())"
                    ),
                    {"e": uuid},
                )

        _run([], migration_engine, "upgrade", "head")

        with migration_engine.connect() as conn:
            states = [
                r.state
                for r in conn.execute(
                    text(
                        "SELECT state FROM processed_events "
                        "WHERE consumer_name = 'legacy' ORDER BY event_id"
                    )
                ).all()
            ]
        assert states == ["processed", "processed"]

    def test_completed_state_requires_full_payload(
        self, migration_engine: Engine
    ) -> None:
        _run([], migration_engine, "upgrade", "head")
        with pytest.raises(Exception):
            with migration_engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO processed_events "
                        "(event_id, consumer_name, processed_at, "
                        " updated_at, state) "
                        "VALUES ('key-bad', 'Checkout', NOW(), NOW(), "
                        "        'completed')"
                    )
                )

    def test_in_progress_state_accepts_no_payload(
        self, migration_engine: Engine
    ) -> None:
        _run([], migration_engine, "upgrade", "head")
        with migration_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO processed_events "
                    "(event_id, consumer_name, processed_at, updated_at, state) "
                    "VALUES ('key-progress', 'Checkout', NOW(), NOW(), "
                    "        'in_progress')"
                )
            )
        with migration_engine.connect() as conn:
            row = conn.execute(
                text("SELECT state FROM processed_events WHERE event_id = :e"),
                {"e": "key-progress"},
            ).one()
        assert row.state == "in_progress"

    def test_completed_state_with_full_payload(self, migration_engine: Engine) -> None:
        _run([], migration_engine, "upgrade", "head")
        with migration_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO processed_events "
                    "(event_id, consumer_name, processed_at, updated_at, state, "
                    " payload_hash, response_status, response_body) "
                    "VALUES ('key-done', 'Checkout', NOW(), NOW(), 'completed',"
                    "        :h, 201, :b)"
                ),
                {"h": "0" * 64, "b": '{"status": "confirmed"}'},
            )
        with migration_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT payload_hash, response_status, response_body "
                    "FROM processed_events WHERE event_id = 'key-done'"
                )
            ).one()
        assert row.payload_hash == "0" * 64
        assert row.response_status == 201
        assert row.response_body["status"] == "confirmed"

    def test_downgrade_restores_legacy_shape(self, migration_engine: Engine) -> None:
        _run([], migration_engine, "upgrade", "head")
        with migration_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO processed_events "
                    "(event_id, consumer_name, processed_at, updated_at, state) "
                    "VALUES ('33333333-3333-3333-3333-333333333333',"
                    "        'Checkout', NOW(), NOW(), 'in_progress')"
                )
            )

        # The chain has grown since S1a (S2 adds payments.failure_reason), so
        # downgrade to the explicit pre-S1a base to assert the legacy shape.
        _run([], migration_engine, "downgrade", "4d6e7a8b9c0f")

        cols = _column_info(migration_engine, "processed_events")
        assert cols["event_id"]["data_type"] == "uuid"
        for dropped in (
            "payload_hash",
            "response_status",
            "response_body",
            "updated_at",
            "state",
        ):
            assert dropped not in cols
        cols_payments = _column_info(migration_engine, "payments")
        assert cols_payments["amount"]["data_type"] == "double precision"
        with migration_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT event_id FROM processed_events "
                    "WHERE consumer_name = 'Checkout'"
                )
            ).one()
        assert str(row.event_id) == "33333333-3333-3333-3333-333333333333"
