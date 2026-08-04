"""Extend checkout idempotency: durable response cache + payments.amount NUMERIC(11,2)

Adds the response-cache columns and ``state`` to ``processed_events``,
backfills legacy UUID rows with ``state='processed'``, widens
``payments.amount`` to ``NUMERIC(11,2)``, and requires any ``state='completed'``
row to carry its hash, status, and body so the durable replay cache can never
hold a partial record.

Revision ID: 7b8c9d0e1f2a
Revises: 4d6e7a8b9c0f
Create Date: 2026-07-31 21:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "7b8c9d0e1f2a"
down_revision: Union[str, Sequence[str], None] = "4d6e7a8b9c0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COMPLETED_CHECK = (
    "((state <> 'completed') OR "
    "(payload_hash IS NOT NULL AND response_status IS NOT NULL "
    " AND response_body IS NOT NULL))"
)


def upgrade() -> None:
    # ---- payments.amount: Float -> NUMERIC(11,2) ---------------------------
    op.alter_column(
        "payments",
        "amount",
        existing_type=sa.Float(),
        type_=sa.Numeric(11, 2),
        existing_nullable=False,
        postgresql_using="amount::numeric(11,2)",
    )

    # ---- processed_events.event_id: UUID -> Text ----------------------------
    op.alter_column(
        "processed_events",
        "event_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        type_=sa.Text(),
        existing_nullable=False,
        postgresql_using="event_id::text",
    )

    # ---- new columns -------------------------------------------------------
    op.add_column(
        "processed_events",
        sa.Column("payload_hash", sa.CHAR(length=64), nullable=True),
    )
    op.add_column(
        "processed_events",
        sa.Column("response_status", sa.Integer(), nullable=True),
    )
    op.add_column(
        "processed_events",
        sa.Column(
            "response_body",
            sa.dialects.postgresql.JSON(),
            nullable=True,
        ),
    )
    op.add_column(
        "processed_events",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "processed_events",
        sa.Column(
            "state",
            sa.Text(),
            nullable=False,
            server_default="processed",
        ),
    )
    op.create_check_constraint(
        "ck_processed_events_state",
        "processed_events",
        "state IN ('processed', 'in_progress', 'completed')",
    )
    op.create_check_constraint(
        "ck_processed_events_completed_payload",
        "processed_events",
        _COMPLETED_CHECK,
    )

    # ---- backfill -----------------------------------------------------------
    op.execute("UPDATE processed_events SET state = 'processed' WHERE state IS NULL")


def downgrade() -> None:
    op.drop_constraint("ck_processed_events_completed_payload", "processed_events")
    op.drop_constraint("ck_processed_events_state", "processed_events")
    op.drop_column("processed_events", "state")
    op.drop_column("processed_events", "updated_at")
    op.drop_column("processed_events", "response_body")
    op.drop_column("processed_events", "response_status")
    op.drop_column("processed_events", "payload_hash")

    op.alter_column(
        "processed_events",
        "event_id",
        existing_type=sa.Text(),
        type_=sa.dialects.postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        postgresql_using="event_id::uuid",
    )

    op.alter_column(
        "payments",
        "amount",
        existing_type=sa.Numeric(11, 2),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="amount::double precision",
    )
