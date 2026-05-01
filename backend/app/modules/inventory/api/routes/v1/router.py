"""Inventory v1 routes."""
from fastapi import APIRouter

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/_health")
def inventory_healthcheck() -> dict[str, str]:
    return {"module": "inventory", "status": "ok", "version": "v1"}

