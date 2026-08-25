import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.messaging_runtime import create_messaging_runtime
from app.modules.checkout.api.container import checkout_container
from app.modules.checkout.api.routes import router as checkout_router
from app.modules.inventory.api.container import inventory_container
from app.modules.inventory.api.routes import router as inventory_router
from app.modules.notifications.api.container import notifications_container
from app.modules.notifications.api.routes import router as notifications_router
from app.modules.orders.api.container import orders_container
from app.modules.orders.api.routes import router as orders_router
from app.modules.payments.api.container import payments_container
from app.modules.payments.api.routes import router as payments_router
from app.shared.config import get_settings
from app.shared.db.session import get_session_factory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    settings = get_settings()
    session_factory = get_session_factory()
    runtime = create_messaging_runtime(settings, session_factory)
    try:
        await runtime.start()
    except Exception:  # noqa: BLE001
        logger.exception("messaging_runtime_start_failed")
    try:
        yield
    finally:
        try:
            await asyncio.wait_for(runtime.stop(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("messaging_runtime_shutdown_timeout")
        except Exception:  # noqa: BLE001
            logger.exception("messaging_runtime_stop_failed")


def create_app() -> FastAPI:
    settings = get_settings()

    orders_container.wire(modules=["app.modules.orders.api.routes"])
    inventory_container.wire(modules=["app.modules.inventory.api.routes"])
    notifications_container.wire(modules=["app.modules.notifications.api.routes"])
    payments_container.wire(modules=["app.modules.payments.api.routes"])
    checkout_container.wire(modules=["app.modules.checkout.api.routes"])

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["health"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    app.include_router(orders_router, prefix="/api/v1")
    app.include_router(inventory_router, prefix="/api/v1")
    app.include_router(payments_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(checkout_router, prefix="/api/v1")

    return app


app = create_app()
