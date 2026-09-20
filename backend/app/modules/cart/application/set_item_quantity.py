"""SetCartItemQuantity use case: set an absolute line quantity."""

from uuid import UUID

from app.modules.cart.application.cart_view import CartView, build_cart_view
from app.modules.cart.domain.entities import CartLine
from app.modules.cart.domain.errors import (
    CartItemNotFoundError,
    ProductNotFoundError,
)
from app.modules.cart.domain.repository import CartRepository
from app.modules.cart.domain.services import validate_quantity
from app.modules.catalog.domain.repository import ProductRepository


class SetCartItemQuantity:
    def __init__(
        self,
        carts: CartRepository,
        products: ProductRepository,
    ) -> None:
        self._carts = carts
        self._products = products

    async def execute(
        self, customer_id: UUID, product_id: str, quantity: int
    ) -> CartView:
        validate_quantity(quantity)
        product = await self._products.get_by_id(product_id)
        if product is None or not product.active:
            raise ProductNotFoundError("Product not found")

        cart = await self._carts.get_or_create(customer_id)
        current = await self._carts.get_line(cart.id, product_id)
        if current is None:
            raise CartItemNotFoundError("Cart item not found")
        await self._carts.save_line(
            CartLine(cart_id=cart.id, product_id=product_id, quantity=quantity)
        )

        lines = await self._carts.list_lines(cart.id)
        catalog = {}
        for line in lines:
            fetched = await self._products.get_by_id(line.product_id)
            if fetched is not None and fetched.active:
                catalog[line.product_id] = fetched
        catalog[product_id] = product
        return build_cart_view(cart, lines, catalog)
