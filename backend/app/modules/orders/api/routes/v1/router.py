"""Orders v1 routes."""
from fastapi import APIRouter

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/_health")
def orders_healthcheck() -> dict[str, str]:
    return {"module": "orders", "status": "ok", "version": "v1"}

