"""IAM dependency injection container."""

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.iam.application import passwords as password_service
from app.modules.iam.application import refresh_tokens as refresh_service
from app.modules.iam.application import tokens as token_service
from app.modules.iam.application.authenticate_user import authenticate_user
from app.modules.iam.application.register_user import register_user
from app.modules.iam.application.refresh_tokens import (
    issue_refresh_token,
    rotate_refresh_token,
)
from app.modules.iam.infrastructure.sqlalchemy_refresh_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from app.modules.iam.infrastructure.sqlalchemy_repository import (
    SqlAlchemyUserRepository,
)


class IamContainer(containers.DeclarativeContainer):
    """IAM module container wiring repository, services, and use cases."""

    session = providers.Dependency(instance_of=AsyncSession)

    user_repo = providers.Factory(SqlAlchemyUserRepository, session=session)
    refresh_token_repo = providers.Factory(
        SqlAlchemyRefreshTokenRepository, session=session
    )
    password_service = providers.Object(password_service)
    token_service = providers.Object(token_service)
    refresh_service = providers.Object(refresh_service)
    register_user = providers.Object(register_user)
    authenticate_user = providers.Object(authenticate_user)
    issue_refresh_token = providers.Object(issue_refresh_token)
    rotate_refresh_token = providers.Object(rotate_refresh_token)


iam_container = IamContainer()
