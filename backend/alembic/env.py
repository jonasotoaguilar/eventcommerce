from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

from app.shared.config import get_settings
from app.shared.db.base import Base

# Import all models so they register with Base.metadata
from app.modules.orders.infrastructure.models import (  # noqa: F401
    OrderItemModel,
    OrderModel,
)
from app.modules.inventory.infrastructure.models import InventoryModel  # noqa: F401
from app.modules.payments.infrastructure.models import PaymentModel  # noqa: F401
from app.modules.notifications.infrastructure.models import NotificationModel  # noqa: F401
from app.shared.events.models import DomainEventModel  # noqa: F401
from app.shared.messaging.models import (  # noqa: F401
    OutboxEventModel,
    ProcessedEventModel,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Return a sync database URL for Alembic.

    The application uses ``postgresql+psycopg`` (async-capable driver).
    Alembic needs a synchronous engine, but psycopg v3 works fine with
    a regular ``create_engine`` as long as we do not use the async APIs.
    """
    settings = get_settings()
    url: str = str(settings.database_url)
    if url.startswith("postgresql+asyncpg"):
        url = url.replace("postgresql+asyncpg", "postgresql+psycopg", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    url = get_database_url()
    connectable = create_engine(url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
