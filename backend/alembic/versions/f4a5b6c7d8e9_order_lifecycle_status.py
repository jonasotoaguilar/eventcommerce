"""Enforce five-state order lifecycle statuses (U1 expand-order-state-machine).

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-20 00:00:00.000000

Adds a CHECK constraint on ``orders.status`` so the database enforces the
same five-state lifecycle as the orders domain contract:
pending, inventory_reserved, payment_authorized, confirmed, cancelled.
Existing terminal statuses (pending/confirmed/cancelled) already satisfy
the constraint, so no backfill is required. No columns are added or
altered.

"""

from typing import Sequence, Union

from alembic import op


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STATUS_CHECK = (
    "status IN ("
    "'pending', "
    "'inventory_reserved', "
    "'payment_authorized', "
    "'confirmed', "
    "'cancelled'"
    ")"
)


def upgrade() -> None:
    op.create_check_constraint(
        "ck_orders_status_lifecycle",
        "orders",
        _STATUS_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint("ck_orders_status_lifecycle", "orders")
