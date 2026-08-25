from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.app import create_app


def test_health_when_broker_down_non_fatal():
    rt = AsyncMock()
    rt.start = AsyncMock(side_effect=Exception("broker down"))
    rt.stop = AsyncMock()
    with patch("app.app.create_messaging_runtime", return_value=rt):
        app = create_app()
        with TestClient(app) as client:
            r = client.get("/health")
            assert r.status_code == 200
            assert r.json()["status"] == "ok"
            rt.start.assert_awaited_once()
        rt.stop.assert_awaited_once()


def test_lifespan_start_before_and_stop_after_serving():
    rt = AsyncMock()
    order: list[str] = []

    async def _start():
        order.append("start")

    async def _stop():
        order.append("stop")

    rt.start.side_effect = _start
    rt.stop.side_effect = _stop
    with patch("app.app.create_messaging_runtime", return_value=rt):
        app = create_app()
        with TestClient(app) as client:
            order.append("serving")
            assert client.get("/health").status_code == 200
            assert order[0] == "start"
            assert "serving" in order
        assert order[-1] == "stop"
        rt.start.assert_awaited_once()
        rt.stop.assert_awaited_once()


def test_health_preserves_composition():
    rt = AsyncMock()
    rt.start = AsyncMock()
    rt.stop = AsyncMock()
    with patch("app.app.create_messaging_runtime", return_value=rt):
        app = create_app()
        with TestClient(app) as client:
            assert client.get("/health").json()["service"] == app.title
            paths = [getattr(r, "path", "") for r in app.routes]
            assert "/health" in paths
