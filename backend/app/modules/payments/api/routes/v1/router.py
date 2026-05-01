"""Payments v1 routes."""
from fastapi import APIRouter

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/_health")
def payments_healthcheck() -> dict[str, str]:
    return {"module": "payments", "status": "ok", "version": "v1"}

