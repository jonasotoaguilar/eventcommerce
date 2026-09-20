"""RemoveCartItem use case: idempotent line removal.

Deleting a missing line still returns the cart with 200 so retries and
double-clicks are safe; use PATCH semantics (404) when the caller must
know whether the line existed.
"""

from uuid import UUID

from app.modules.cart.application.cart_view import CartView, build_cart_view
from app.modules.cart.domain.repository import CartRepository
from app.modules.catalog.domain.repository import ProductRepository


class RemoveCartItem:
    def __init__(
        self,
        carts: CartRepository,
        products: ProductRepository,
    ) -> None:
        self._carts = carts
        self._products = products

    async def execute(self, customer_id: UUID, product_id: str) -> CartView:
        cart = await self._carts.get_or_create(customer_id)
        await self._carts.delete_line(cart.id, product_id)
        lines = await self._carts.list_lines(cart.id)
        catalog = {}
        for line in lines:
            product = await self._products.get_by_id(line.product_id)
            if product is not None and product.active:
                catalog[line.product_id] = product
        return build_cart_view(cart, lines, catalog)
