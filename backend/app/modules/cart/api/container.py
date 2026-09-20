"""Cart dependency injection container."""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.application.add_item import AddCartItem
from app.modules.cart.application.get_cart import GetCart
from app.modules.cart.application.remove_item import RemoveCartItem
from app.modules.cart.application.set_item_quantity import SetCartItemQuantity
from app.modules.cart.infrastructure.sqlalchemy_repository import (
    SqlAlchemyCartRepository,
)
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)


class CartContainer(containers.DeclarativeContainer):
    """Cart module container wiring repositories and use cases."""

    session = providers.Dependency(instance_of=AsyncSession)

    cart_repo = providers.Factory(SqlAlchemyCartRepository, session=session)
    product_repo = providers.Factory(SqlAlchemyProductRepository, session=session)

    get_cart = providers.Factory(GetCart, carts=cart_repo, products=product_repo)
    add_item = providers.Factory(AddCartItem, carts=cart_repo, products=product_repo)
    set_quantity = providers.Factory(
        SetCartItemQuantity, carts=cart_repo, products=product_repo
    )
    remove_item = providers.Factory(
        RemoveCartItem, carts=cart_repo, products=product_repo
    )


cart_container = CartContainer()
