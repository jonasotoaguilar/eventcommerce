"""Notifications v1 routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/_health")
def notifications_healthcheck() -> dict[str, str]:
    return {"module": "notifications", "status": "ok", "version": "v1"}
