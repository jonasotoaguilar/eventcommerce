"""Catalog SQLAlchemy ORM models."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


class ProductModel(Base):
    __tablename__ = "catalog_products"
    # Mirrors backend/alembic/versions/d2e3f4a5b6c7_add_catalog_products.py
    # (the migration stays authoritative); kept here so create_all-based
    # test schemas carry the same invariants.
    __table_args__ = (
        CheckConstraint(
            "char_length(id) BETWEEN 1 AND 128",
            name="ck_catalog_products_id_len",
        ),
        CheckConstraint(
            "char_length(name) BETWEEN 1 AND 255",
            name="ck_catalog_products_name_len",
        ),
        CheckConstraint(
            "price >= 0 AND price <= 999999999.99",
            name="ck_catalog_products_price_range",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_catalog_products_currency"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
