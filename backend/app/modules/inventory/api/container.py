"""Inventory dependency injection container."""

from dependency_injector import containers


class InventoryContainer(containers.DeclarativeContainer):
    """Inventory module container."""

    wiring_config = containers.WiringConfiguration(
        modules=["app.modules.inventory.api.routes"]
    )


inventory_container = InventoryContainer()
