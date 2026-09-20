"""Container wiring tests for the catalog module (U1)."""

from typing import cast

import pytest
from dependency_injector import errors
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.api.container import catalog_container
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


class _FakeSession(AsyncSession):
    def __init__(self) -> None:
        pass


def test_catalog_container_requires_a_request_session_override() -> None:
    with pytest.raises(errors.Error):
        catalog_container.create_product()
    with pytest.raises(errors.Error):
        catalog_container.get_product()


def test_catalog_container_wires_use_cases_to_the_request_session() -> None:
    session = _FakeSession()
    catalog_container.session.override(session)
    try:
        create = catalog_container.create_product()
        get = catalog_container.get_product()
        listing = catalog_container.list_products()
        update = catalog_container.update_product()
    finally:
        catalog_container.session.reset_override()

    assert isinstance(create, CreateProduct)
    assert isinstance(get, GetProduct)
    assert isinstance(listing, ListProducts)
    assert isinstance(update, UpdateProduct)
    assert cast(SqlAlchemyProductRepository, create._repository)._session is session
    assert cast(SqlAlchemyInventoryRepository, create._inventory)._session is session
    assert cast(SqlAlchemyProductRepository, get._repository)._session is session
