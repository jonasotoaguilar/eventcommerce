from app.shared.config import get_settings

import uvicorn


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )
