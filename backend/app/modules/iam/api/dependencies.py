"""IAM FastAPI dependencies: bearer auth with {detail} error envelope."""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.modules.iam.application.tokens import CurrentUser, verify_token
from app.modules.iam.domain.errors import InvalidTokenError, JwtConfigurationError
from app.shared.config.settings import get_settings

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """Return the verified caller; 401 when missing/invalid/expired."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        return verify_token(credentials.credentials, settings=get_settings())
    except JwtConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured",
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


def require_roles(*roles: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    """Return a dependency allowing only callers holding one of roles (403)."""

    async def _checker(
        current: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current

    return _checker
