"""Inventory dependency injection container."""

from dependency_injector import containers


class InventoryContainer(containers.DeclarativeContainer):
    """Inventory module container."""


inventory_container = InventoryContainer()
