"""Live catalog projection of a cart.

Lines are projected from current catalog prices on every read: the cart
stores only ``(product_id, quantity)`` while name, unit price, currency,
and line totals always reflect the catalog. Lines whose product is
missing or inactive are never exposed and never included in the
subtotal. ``currency`` is ``None`` for an empty (or fully hidden)
cart; otherwise every visible line shares the cart currency (enforced
on add).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.modules.cart.domain.entities import Cart, CartLine
from app.modules.catalog.domain.entities import Product

EMPTY_SUBTOTAL = Decimal("0.00")


@dataclass(frozen=True)
class CartLineView:
    product_id: str
    name: str
    quantity: int
    unit_price: Decimal
    currency: str
    line_total: Decimal


@dataclass(frozen=True)
class CartView:
    cart_id: UUID
    customer_id: UUID
    items: list[CartLineView] = field(default_factory=list)
    subtotal: Decimal = EMPTY_SUBTOTAL
    currency: str | None = None


def build_cart_view(
    cart: Cart,
    lines: list[CartLine],
    products: dict[str, Product],
) -> CartView:
    """Project stored lines onto live, active catalog data.

    Lines whose product row vanished out-of-band are skipped defensively
    so one stale line can never fail the whole cart read; lines whose
    product is inactive are hidden the same way so a deactivated product
    is never exposed and never included in the subtotal.
    """
    items: list[CartLineView] = []
    for line in lines:
        product = products.get(line.product_id)
        if product is None or not product.active:
            continue
        line_total = product.price * line.quantity
        items.append(
            CartLineView(
                product_id=line.product_id,
                name=product.name,
                quantity=line.quantity,
                unit_price=product.price,
                currency=product.currency,
                line_total=line_total,
            )
        )
    subtotal = sum((item.line_total for item in items), EMPTY_SUBTOTAL)
    currency = items[0].currency if items else None
    return CartView(
        cart_id=cart.id,
        customer_id=cart.customer_id,
        items=items,
        subtotal=subtotal,
        currency=currency,
    )
