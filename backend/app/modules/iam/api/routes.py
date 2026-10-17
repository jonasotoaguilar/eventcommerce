"""IAM API routes: register (201/409), login (200/401), refresh, me."""

from collections.abc import AsyncGenerator, Awaitable, Callable

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.api.container import IamContainer, iam_container
from app.modules.iam.api.dependencies import get_current_user
from app.modules.iam.api.rate_limit import (
    enforce_login_rate_limit,
    enforce_register_rate_limit,
)
from app.modules.iam.api.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.modules.iam.application.tokens import CurrentUser, issue_token
from app.modules.iam.domain.entities import User
from app.modules.iam.domain.errors import (
    DuplicateEmailError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.modules.iam.domain.repository import RefreshTokenRepository, UserRepository
from app.shared.db.session import get_db_session

router = APIRouter(prefix="/iam", tags=["iam"])

RegisterUserFn = Callable[..., Awaitable[User]]
AuthenticateUserFn = Callable[..., Awaitable[User]]
IssueRefreshTokenFn = Callable[..., Awaitable[str]]
RotateRefreshTokenFn = Callable[..., Awaitable[tuple[User, str]]]


async def _iam_db_session(
    session: AsyncSession = Depends(get_db_session),
) -> AsyncGenerator[AsyncSession, None]:
    """Yield a DB session after overriding the IAM container's session provider."""
    iam_container.session.override(session)
    try:
        yield session
    finally:
        iam_container.session.reset_override()


@router.post("/register", status_code=status.HTTP_201_CREATED)
@inject
async def register(
    body: RegisterRequest,
    _rate_limit: None = Depends(enforce_register_rate_limit),
    session: AsyncSession = Depends(_iam_db_session),
    repository: UserRepository = Depends(Provide[IamContainer.user_repo]),
    register_user: RegisterUserFn = Depends(Provide[IamContainer.register_user]),
) -> UserResponse:
    try:
        user = await register_user(repository, str(body.email), body.password)
    except DuplicateEmailError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc
    await session.commit()
    return UserResponse(user_id=user.id, email=user.email, role=user.role)


@router.post("/login")
@inject
async def login(
    body: LoginRequest,
    _rate_limit: None = Depends(enforce_login_rate_limit),
    # Load-bearing: binds the request session into the container for the repo.
    session: AsyncSession = Depends(_iam_db_session),
    repository: UserRepository = Depends(Provide[IamContainer.user_repo]),
    refresh_repository: RefreshTokenRepository = Depends(
        Provide[IamContainer.refresh_token_repo]
    ),
    authenticate_user: AuthenticateUserFn = Depends(
        Provide[IamContainer.authenticate_user]
    ),
    issue_refresh_token: IssueRefreshTokenFn = Depends(
        Provide[IamContainer.issue_refresh_token]
    ),
) -> TokenResponse:
    """Authenticate with generic 401; never distinguishes the failure cause."""
    try:
        user = await authenticate_user(repository, str(body.email), body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from exc
    refresh_token = await issue_refresh_token(refresh_repository, user.id)
    await session.commit()
    return TokenResponse(
        access_token=issue_token(user.id, user.email, user.role),
        refresh_token=refresh_token,
    )


@router.post("/refresh")
@inject
async def refresh(
    body: RefreshRequest,
    # Load-bearing: binds the request session into the container for the repo.
    session: AsyncSession = Depends(_iam_db_session),
    repository: UserRepository = Depends(Provide[IamContainer.user_repo]),
    refresh_repository: RefreshTokenRepository = Depends(
        Provide[IamContainer.refresh_token_repo]
    ),
    rotate_refresh_token: RotateRefreshTokenFn = Depends(
        Provide[IamContainer.rotate_refresh_token]
    ),
) -> TokenResponse:
    """Rotate one refresh token; every failure shares a generic 401."""
    try:
        user, successor = await rotate_refresh_token(
            repository, refresh_repository, body.refresh_token
        )
    except InvalidTokenError as exc:
        # A replay revokes its family inside the use case; persist that
        # revocation even though the answer is a rejection.
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    await session.commit()
    return TokenResponse(
        access_token=issue_token(user.id, user.email, user.role),
        refresh_token=successor,
    )


@router.get("/me")
async def me(current: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user_id=current.user_id, email=current.email, role=current.role)
