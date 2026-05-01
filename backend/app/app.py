from fastapi import FastAPI

from app.modules.inventory.api.routes.v1.router import router as inventory_router
from app.modules.notifications.api.routes.v1.router import router as notifications_router
from app.modules.orders.api.routes.v1.router import router as orders_router
from app.modules.payments.api.routes.v1.router import router as payments_router
from app.shared.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
    )

    @app.get("/health", tags=["health"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    app.include_router(orders_router, prefix="/api/v1")
    app.include_router(inventory_router, prefix="/api/v1")
    app.include_router(payments_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")

    return app


app = create_app()
