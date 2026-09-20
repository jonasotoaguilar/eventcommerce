"""GetCart use case: return the caller's cart, creating it lazily."""

from uuid import UUID

from app.modules.cart.application.cart_view import CartView, build_cart_view
from app.modules.cart.domain.repository import CartRepository
from app.modules.catalog.domain.repository import ProductRepository


class GetCart:
    def __init__(
        self,
        carts: CartRepository,
        products: ProductRepository,
    ) -> None:
        self._carts = carts
        self._products = products

    async def execute(self, customer_id: UUID) -> CartView:
        cart = await self._carts.get_or_create(customer_id)
        lines = await self._carts.list_lines(cart.id)
        catalog: dict = {}
        for line in lines:
            product = await self._products.get_by_id(line.product_id)
            if product is not None and product.active:
                catalog[line.product_id] = product
        return build_cart_view(cart, lines, catalog)
