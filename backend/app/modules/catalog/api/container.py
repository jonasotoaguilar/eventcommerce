"""Catalog dependency injection container."""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.application.create_product import CreateProduct
from app.modules.catalog.application.get_product import GetProduct
from app.modules.catalog.application.list_products import ListProducts
from app.modules.catalog.application.update_product import UpdateProduct
from app.modules.catalog.infrastructure.sqlalchemy_repository import (
    SqlAlchemyProductRepository,
)
from app.modules.inventory.infrastructure.sqlalchemy_repository import (
    SqlAlchemyInventoryRepository,
)


class CatalogContainer(containers.DeclarativeContainer):
    """Catalog module container wiring repositories and use cases."""

    session = providers.Dependency(instance_of=AsyncSession)

    product_repo = providers.Factory(SqlAlchemyProductRepository, session=session)
    inventory_repo = providers.Factory(SqlAlchemyInventoryRepository, session=session)

    create_product = providers.Factory(
        CreateProduct,
        repository=product_repo,
        inventory_repository=inventory_repo,
    )
    update_product = providers.Factory(UpdateProduct, repository=product_repo)
    get_product = providers.Factory(GetProduct, repository=product_repo)
    list_products = providers.Factory(ListProducts, repository=product_repo)


catalog_container = CatalogContainer()
