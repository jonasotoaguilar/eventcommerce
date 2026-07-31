"""Inventory SQLAlchemy ORM models."""

from sqlalchemy import Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db.base import Base


class InventoryModel(Base):
    __tablename__ = "inventory"

    product_id: Mapped[str] = mapped_column(Text, primary_key=True)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
