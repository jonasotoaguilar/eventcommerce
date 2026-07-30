"""Drop redundant uq_processed_event unique constraint

The composite primary key on (event_id, consumer_name) already enforces
uniqueness.  The separate unique constraint is redundant.

Revision ID: 4d6e7a8b9c0f
Revises: 2c4f8a1b3e6d
Create Date: 2026-07-30 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "4d6e7a8b9c0f"
down_revision: Union[str, Sequence[str], None] = "2c4f8a1b3e6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_processed_event", "processed_events", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_processed_event",
        "processed_events",
        ["event_id", "consumer_name"],
    )
