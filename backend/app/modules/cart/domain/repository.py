"""Cart repository protocol."""

from typing import Protocol
from uuid import UUID

from app.modules.cart.domain.entities import Cart, CartLine


class CartRepository(Protocol):
    async def get_by_customer(self, customer_id: UUID) -> Cart | None: ...
    async def get_by_id(self, cart_id: UUID) -> Cart | None:
        """Return the cart with this id, or None when absent.

        Unlike ``get_or_create`` this never creates: cart-backed checkout
        uses it to load a caller-supplied id without side effects.
        """
        ...

    async def get_or_create(self, customer_id: UUID) -> Cart:
        """Return the caller's cart, creating it lazily when absent.

        The returned row is locked (or newly inserted) so concurrent
        line increments serialize on the cart row.
        """
        ...

    async def list_lines(self, cart_id: UUID) -> list[CartLine]: ...
    async def get_line(self, cart_id: UUID, product_id: str) -> CartLine | None: ...
    async def count_lines(self, cart_id: UUID) -> int: ...
    async def save_line(self, line: CartLine) -> None: ...
    async def delete_line(self, cart_id: UUID, product_id: str) -> bool: ...
    async def clear_lines(self, cart_id: UUID) -> None:
        """Remove every line of one cart.

        Checkout calls this after a confirmed cart-backed order, in the
        same transaction as the commerce commit; cancellations never call
        it so the cart stays intact.
        """
        ...
