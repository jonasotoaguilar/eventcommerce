"""AddCartItem use case: add a line, incrementing when it exists."""

from uuid import UUID

from app.modules.cart.application.cart_view import CartView, build_cart_view
from app.modules.cart.domain.entities import CartLine
from app.modules.cart.domain.errors import (
    CartLimitExceededError,
    CurrencyMismatchError,
    ProductNotFoundError,
)
from app.modules.cart.domain.repository import CartRepository
from app.modules.cart.domain.services import (
    MAX_LINES,
    MAX_QUANTITY,
    validate_quantity,
)
from app.modules.catalog.domain.repository import ProductRepository


class AddCartItem:
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
        lines = await self._carts.list_lines(cart.id)
        catalog = {}
        for line in lines:
            existing_product = await self._products.get_by_id(line.product_id)
            # Only active products count: hidden (inactive) lines neither
            # expose data nor pin the cart currency.
            if existing_product is not None and existing_product.active:
                catalog[line.product_id] = existing_product
        cart_currency = next(
            (
                catalog[line.product_id].currency
                for line in lines
                if line.product_id in catalog
            ),
            None,
        )
        if cart_currency is not None and product.currency != cart_currency:
            raise CurrencyMismatchError(f"Cart holds {cart_currency} products only")

        current = next((line for line in lines if line.product_id == product_id), None)
        if current is not None:
            new_quantity = current.quantity + quantity
            if new_quantity > MAX_QUANTITY:
                raise CartLimitExceededError("Cart line quantity cannot exceed 10000")
            await self._carts.save_line(
                CartLine(
                    cart_id=cart.id,
                    product_id=product_id,
                    quantity=new_quantity,
                )
            )
        else:
            if len(lines) >= MAX_LINES:
                raise CartLimitExceededError(
                    "Cart cannot hold more than 100 unique products"
                )
            await self._carts.save_line(
                CartLine(cart_id=cart.id, product_id=product_id, quantity=quantity)
            )

        lines = await self._carts.list_lines(cart.id)
        for line in lines:
            if line.product_id not in catalog:
                fetched = await self._products.get_by_id(line.product_id)
                if fetched is not None:
                    catalog[line.product_id] = fetched
        catalog[product_id] = product
        return build_cart_view(cart, lines, catalog)
