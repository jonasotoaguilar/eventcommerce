"""Add catalog products table (U1 catalog-cart).

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-20 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "catalog_products",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "char_length(id) BETWEEN 1 AND 128", name="ck_catalog_products_id_len"
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 255", name="ck_catalog_products_name_len"
        ),
        sa.CheckConstraint(
            "price >= 0 AND price <= 999999999.99",
            name="ck_catalog_products_price_range",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_catalog_products_currency"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_catalog_products_active",
        "catalog_products",
        ["active"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_products_active", table_name="catalog_products")
    op.drop_table("catalog_products")
