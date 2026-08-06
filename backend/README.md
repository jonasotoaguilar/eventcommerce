# EventCommerce Backend

Python backend for EventCommerce with:

- uv
- FastAPI
- Pydantic Settings
- SQLAlchemy (async)
- dependency-injector
- Pyrefly

## Run

```bash
uv sync
cp .env.example .env
uv run eventcommerce-backend
```

Default expected database:

```env
EVENTCOMMERCE_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/eventcommerce
```

## Test and quality

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check
```

## Structure

```text
app/
  modules/
    orders/
      api/            — routes.py, schemas.py, container.py
      application/
      domain/
      infrastructure/
    checkout/
      api/
      application/
    inventory/
      api/
      application/
      domain/
      infrastructure/
    payments/
      api/
      application/
      domain/
      infrastructure/
    notifications/
      api/
      application/
      domain/
      infrastructure/
  shared/
    config/
    db/
    events/           — shared event store (domain_events)
    messaging/        — envelope, outbox, idempotency, publisher, worker
```

Modules follow a flat layout: `api/routes.py`, `api/schemas.py`, and `api/container.py` (dependency-injector) instead of nested `api/routes/v1/router.py`. Migrations live in `alembic/versions/`.
