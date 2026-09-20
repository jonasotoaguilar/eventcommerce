"""Catalog API schemas."""

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ProductCreateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal = Field(ge=Decimal("0"), le=Decimal("999999999.99"))
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    active: bool = True

    @field_validator("price")
    @classmethod
    def _max_two_decimals(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Price must be finite")
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -2:
            raise ValueError("Price must have at most 2 decimals")
        return value


class ProductUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    price: Decimal | None = Field(
        default=None, ge=Decimal("0"), le=Decimal("999999999.99")
    )
    currency: str | None = Field(
        default=None, min_length=3, max_length=3, pattern=r"^[A-Z]{3}$"
    )
    active: bool | None = None

    @field_validator("price")
    @classmethod
    def _max_two_decimals(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if not value.is_finite():
            raise ValueError("Price must be finite")
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -2:
            raise ValueError("Price must have at most 2 decimals")
        return value


class ProductResponse(BaseModel):
    id: str
    name: str
    description: str | None
    price: Decimal
    currency: str
    active: bool
    created_at: str | None
    updated_at: str | None
