"""Add payments.failure_reason column

Adds the nullable ``failure_reason`` text column to ``payments`` so a
``declined`` Payment persisted by ``ProcessPaymentFailure`` retains the
decline reason across the repository boundary.

Revision ID: 8d9e0f1a2b3c
Revises: 7b8c9d0e1f2a
Create Date: 2026-08-04 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "8d9e0f1a2b3c"
down_revision: Union[str, Sequence[str], None] = "7b8c9d0e1f2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "failure_reason")
