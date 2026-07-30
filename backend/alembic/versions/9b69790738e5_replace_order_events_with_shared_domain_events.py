"""Replace order_events with shared domain_events

Revision ID: 9b69790738e5
Revises: a14ca47ad70f
Create Date: 2026-05-01 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9b69790738e5"
down_revision: Union[str, Sequence[str], None] = "a14ca47ad70f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create shared domain_events table
    op.create_table(
        "domain_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Migrate existing order events into domain_events
    op.execute(
        """
        INSERT INTO domain_events (id, event_id, aggregate_type, aggregate_id, event_type, payload, occurred_at)
        SELECT id, event_id, 'order', order_id::text, event_type, payload, created_at
        FROM order_events
        """
    )

    # Drop old order-specific events table
    op.drop_table("order_events")


def downgrade() -> None:
    """Downgrade schema."""
    # Recreate old order_events table
    op.create_table(
        "order_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Migrate domain events back into order_events (only order aggregates)
    op.execute(
        """
        INSERT INTO order_events (id, order_id, event_id, event_type, payload, created_at)
        SELECT id, aggregate_id::uuid, event_id, event_type, payload, occurred_at
        FROM domain_events
        WHERE aggregate_type = 'order'
        """
    )

    # Drop shared domain_events table
    op.drop_table("domain_events")
