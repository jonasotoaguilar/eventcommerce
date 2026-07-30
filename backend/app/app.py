from fastapi import FastAPI

from app.modules.inventory.api.container import inventory_container
from app.modules.inventory.api.routes import router as inventory_router
from app.modules.notifications.api.container import notifications_container
from app.modules.notifications.api.routes import router as notifications_router
from app.modules.orders.api.container import orders_container
from app.modules.orders.api.routes import router as orders_router
from app.modules.payments.api.container import payments_container
from app.modules.payments.api.routes import router as payments_router
from app.shared.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    orders_container.wire(modules=["app.modules.orders.api.routes"])
    inventory_container.wire(modules=["app.modules.inventory.api.routes"])
    notifications_container.wire(modules=["app.modules.notifications.api.routes"])
    payments_container.wire(modules=["app.modules.payments.api.routes"])

    @app.get("/health", tags=["health"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    app.include_router(orders_router, prefix="/api/v1")
    app.include_router(inventory_router, prefix="/api/v1")
    app.include_router(payments_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")

    return app


app = create_app()
