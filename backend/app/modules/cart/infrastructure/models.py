"""Cart SQLAlchemy ORM models.

``carts.customer_id`` references ``users.id`` (one active cart per
authenticated shopper, no guest carts). ``cart_items`` uses the
composite ``(cart_id, product_id)`` primary key for line uniqueness and
references ``catalog_products.id`` so lines can only point at known
products. Quantity keeps the shared 1..10,000 invariant at the DB level.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


class CartModel(Base):
    __tablename__ = "carts"
    __table_args__ = (UniqueConstraint("customer_id", name="uq_carts_customer_id"),)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
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


class CartItemModel(Base):
    __tablename__ = "cart_items"
    # Mirrors backend/alembic/versions/e3f4a5b6c7d8_add_cart.py
    # (the migration stays authoritative); kept here so create_all-based
    # test schemas carry the same invariants.
    __table_args__ = (
        CheckConstraint(
            "quantity >= 1 AND quantity <= 10000",
            name="ck_cart_items_quantity_range",
        ),
    )

    cart_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("carts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    product_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("catalog_products.id"),
        primary_key=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
