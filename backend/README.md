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

### Order lifecycle (delivered)

- Five states (`pending`, `inventory_reserved`, `payment_authorized`, `confirmed`, `cancelled`) with transitions owned by `backend/app/modules/orders/domain/services.py`; the synchronous `POST /api/v1/checkout` keeps the `pending` → `confirmed` compatibility shortcut.
- Event-driven path: `OrderCreated` → inventory reservation → `inventory_reserved`/`cancelled`, `OrderInventoryReserved` → catalog-derived payment authorization → `payment_authorized`/`cancelled` (rejection releases inventory), `OrderPaymentAuthorized` → `confirmed`, terminal `OrderConfirmed`/`OrderCancelled` → notifications. Wiring lives in `backend/app/messaging_runtime.py` (six queues on the durable `order.events` TOPIC exchange).
- Operator-only `POST /api/v1/orders/{order_id}/confirm` (`payment_authorized` → `confirmed`) and `POST /api/v1/orders/{order_id}/cancel` (from `pending`/`inventory_reserved`/`payment_authorized`); see `backend/app/modules/orders/api/routes.py`.

```text
app/
  modules/
    orders/
      api/            — routes.py, schemas.py, container.py
      application/
      domain/
      infrastructure/
    iam/
      api/            — routes.py, schemas.py, container.py
    catalog/
      api/            — routes.py, schemas.py, container.py
    cart/
      api/            — routes.py, schemas.py, container.py
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
