# eventcommerce

A product-quality portfolio project: a modular, event-driven commerce backend that demonstrates clean architecture, bounded contexts, and asynchronous integration.

## Status snapshot

### Now

- Modular Python backend in `backend/app/` with `orders`, `inventory`, `payments`, `notifications`, `checkout`, `iam`, `catalog`, and `cart` bounded contexts, wired through `dependency-injector` per-module containers.
- Orders HTTP API: `POST /api/v1/orders`, `GET /api/v1/orders/{order_id}`, `GET /api/v1/orders/{order_id}/timeline`, and operator-only `POST /api/v1/orders/{order_id}/confirm` / `POST /api/v1/orders/{order_id}/cancel`.
- Synchronous checkout at `POST /api/v1/checkout`: creates the order, locks and reserves inventory (row-level `FOR UPDATE`), authorizes payment with a deterministic simulated policy (ADR 0005), and reaches `confirmed` or `cancelled` in one request. It is retained as the synchronous compatibility boundary: the `pending` → `confirmed` shortcut stays owned by checkout alongside the event-driven path.
- Durable idempotency and response cache: `Idempotency-Key` claims with replay detection and `409` on payload mismatch, backed by the `processed_events` table.
- Shared event envelope, event store (`domain_events`), and transactional outbox (`outbox_events`) data structures; checkout and orders persist events to them.
- Quality checks in CI: `ruff check`, `ruff format --check`, `pyrefly check`, and `pytest`.
- Messaging runtime wired into the app lifespan (`backend/app/messaging_runtime.py` + `backend/app/app.py`): outbox scheduler (composite `(status, created_at)` index, `FOR UPDATE SKIP LOCKED` claims), RabbitMQ publisher (persistent delivery, headers, never logs payloads), and AMQP consumer (durable `order.events` TOPIC exchange, six queues, prefetch 1) with idempotent handlers — `OrderCreated` → inventory reservation → `inventory_reserved`/`cancelled`, `OrderInventoryReserved` → catalog-derived payment authorization → `payment_authorized`/`cancelled` (rejection releases inventory), `OrderPaymentAuthorized` → `confirmed`, terminal `OrderConfirmed`/`OrderCancelled` → notifications.
- Chain proof without a broker in the default suite (`backend/app/tests/runtime/test_chain_e2e.py`); real-broker proof gated behind `EVENTCOMMERCE_RUN_RABBITMQ_INTEGRATION=1` (`backend/app/tests/integration/test_rabbitmq_integration.py`, rabbitmq service in CI). Live broker delivery requires RabbitMQ. No production deployment or operations claim.
- IAM bounded context (`backend/app/modules/iam/`): `POST /api/v1/iam/register` (shopper-only, `201`/`409`), `POST /api/v1/iam/login` (30-minute HS256 access JWT, generic `401`), and `GET /api/v1/iam/me` (bearer, `200`/`401`); commerce routes enforce owner-or-operator access from the JWT subject.
- Catalog bounded context (`backend/app/modules/catalog/`): public `GET /api/v1/catalog` (active-only browse) and `GET /api/v1/catalog/{product_id}` (detail; missing and inactive share one `404`), plus operator `POST /api/v1/catalog` / `PATCH /api/v1/catalog/{product_id}` product management. Catalog creation seeds an inventory row at zero stock; operators adjust stock via `POST /api/v1/inventory/{product_id}/adjust`.
- Cart bounded context (`backend/app/modules/cart/`): `GET /api/v1/cart` (lazily created), `POST /api/v1/cart/items`, `PATCH` / `DELETE /api/v1/cart/items/{product_id}` — one persisted cart per authenticated shopper, owner-scoped by the JWT subject, with live subtotal from active catalog prices. Checkout accepts an optional `cart_id` and derives lines, amount, and currency from authoritative catalog pricing; the inline `{items, amount, currency}` shape remains supported.
- **Not yet**: the storefront frontend (the five-state lifecycle and confirm/cancel routes are delivered; see below).

### MVP Target

The remaining commerce journey on a single event-driven backend:

- Storefront UI over the delivered catalog/cart/checkout/orders backend (browse, cart, checkout form, order tracking across the five-state lifecycle).
- The event-driven order path is delivered: `pending` → `inventory_reserved` → `payment_authorized` → `confirmed`/`cancelled` via choreography, with catalog-derived payment authorization, terminal notifications, operator-only confirm/cancel routes, and the synchronous checkout compatibility boundary preserved.

### Future

- Real payment provider adapter.
- Saga orchestration and dead-letter handling.
- Observability stack, runbooks, and a storefront frontend.

## Five-minute path

1. Read the [Product Requirements](./PRD.md) for the vision, personas, and MVP scope.
2. Read [DESIGN.md](./DESIGN.md) for UX flows and component states.
3. Check the [Glossary](./docs/GLOSSARY.md) for event and domain vocabulary.
4. Review the [Decision Records](./docs/adr/) for the non-obvious choices.
5. Browse `backend/app/` to see the code that backs the current state.

## Repository layout

| Path | Purpose |
|------|---------|
| `backend/app/` | FastAPI / SQLAlchemy 2 async backend with bounded contexts |
| `backend/alembic/` | Database migrations |
| `docs/` | Glossary and Architecture Decision Records |
| `openspec/` | SDD change specifications and tasks |
| `frontend/` | Reserved for future frontend work (not created yet) |
| `.github/` | CI and PR templates |

## Documentation index

| Document | Responsibility |
|----------|--------------|
| [PRD.md](./PRD.md) | Vision, problem, personas, journeys, MVP scope, business rules, non-goals, and metrics |
| [DESIGN.md](./DESIGN.md) | Target UX flows, screen inventory, tokens, and states |
| [docs/GLOSSARY.md](./docs/GLOSSARY.md) | Domain terms and event vocabulary |
| [docs/adr/](./docs/adr/) | Architecture Decision Records |

## Contributing

Work is planned and tracked through SDD changes under `openspec/changes/`. Before proposing a code change, open or review the relevant SDD change and make sure your work aligns with the current foundation documents.
