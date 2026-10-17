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
- IAM bounded context (`backend/app/modules/iam/`): `POST /api/v1/iam/register` (shopper-only, `201`/`409`), `POST /api/v1/iam/login` (30-minute HS256 access JWT, generic `401`), and `GET /api/v1/iam/me` (bearer, `200`/`401`); commerce routes enforce owner-or-operator access from the JWT subject. Register and login are rate-limited in process: login allows 10 attempts per account plus 60 per origin per 60-second window, registration allows 20 per origin per 60 seconds (`EVENTCOMMERCE_LOGIN_RATE_LIMIT_ATTEMPTS`, `EVENTCOMMERCE_LOGIN_RATE_LIMIT_HOST_ATTEMPTS`, `EVENTCOMMERCE_LOGIN_RATE_LIMIT_WINDOW_SECONDS`, `EVENTCOMMERCE_REGISTER_RATE_LIMIT_ATTEMPTS`, `EVENTCOMMERCE_REGISTER_RATE_LIMIT_WINDOW_SECONDS`); past the limit the route answers `429` with a `Retry-After` header. The budget is per process, so more than one replica multiplies the effective allowance (see ADR 0007).
- Catalog bounded context (`backend/app/modules/catalog/`): public `GET /api/v1/catalog` (active-only browse) and `GET /api/v1/catalog/{product_id}` (detail; missing and inactive share one `404`), plus operator `POST /api/v1/catalog` / `PATCH /api/v1/catalog/{product_id}` product management. Catalog creation seeds an inventory row at zero stock; operators adjust stock via `POST /api/v1/inventory/{product_id}/adjust`.
- Cart bounded context (`backend/app/modules/cart/`): `GET /api/v1/cart` (lazily created), `POST /api/v1/cart/items`, `PATCH` / `DELETE /api/v1/cart/items/{product_id}` — one persisted cart per authenticated shopper, owner-scoped by the JWT subject, with live subtotal from active catalog prices. Checkout accepts an optional `cart_id` and derives lines, amount, and currency from authoritative catalog pricing; the inline `{items, amount, currency}` shape remains supported.
- Shopper storefront in `frontend/` (React/Vite): catalog browse/detail over `GET /api/v1/catalog`, authenticated persisted cart over the cart API, cart-backed synchronous checkout (`{cart_id}` + fresh `Idempotency-Key` per attempt, terminal `confirmed`/`cancelled` in one request), and order tracking at `/orders/:id` with the exact five statuses (`pending`, `inventory_reserved`, `payment_authorized`, `confirmed`, `cancelled`), chronological timeline, and manual refresh rather than live polling. Auth shell with login/register and route-guarded shopper pages; JWT subject stays authoritative for ownership.
- Operator read model (`backend/app/modules/operator/`, read-only, `operator` role required): `GET /api/v1/operator/orders` (order queue with `status` limited to the five order statuses, `created_from` inclusive, `created_to` exclusive, `limit` 1..200 default 100, `offset` >= 0; each row carries `order_id`, `customer_id`, `status`, `created_at`, `cancel_reason`, `item_count` as summed line quantities, plus `total`/`currency` projected from the latest payment by `(created_at, id)` and `null` when the order has no payment), `GET /api/v1/operator/catalog` (every product including inactive ones ordered by product id, with `available_quantity`/`reserved_quantity` joined from inventory and `null` when the product has no inventory row; same `limit`/`offset` bounds), and `GET /api/v1/operator/payments/simulation` (deterministic decision for `order_id`, `amount` in (0, 999999999.99] with at most two decimals, and a 3-letter `currency`; returns `approved`, `digest_byte`, and `approval_threshold` without touching storage). Anonymous callers get `401`, non-operators get `403`, and unknown `status` or malformed dates get `422`. Operator writes reuse the delivered routes: `PATCH /api/v1/catalog/{product_id}`, `POST /api/v1/inventory/{product_id}/adjust`, and `POST /api/v1/orders/{order_id}/confirm|cancel`.
- Operator console in `frontend/` (`/operator/catalog`, `/operator/orders`, `/operator/payments` behind the `operator` role with `OperatorRoute`): catalog list with edit and stock-adjust actions, order queue with confirm/cancel, and payment simulation panel. On-demand reads with manual refresh rather than live updates; no dashboards, analytics, or user administration.

### MVP Target

The shopper storefront is delivered (see Now): catalog browse/detail, authenticated cart, cart-backed synchronous checkout with idempotency, and order tracking across the five-state lifecycle with manual refresh.

The operator console is delivered (see Now): catalog list with edit and stock-adjust actions, order queue with confirm/cancel, and payment simulation panel over the three operator reads.

The remaining work is not operator-facing: the event-driven order path is delivered — `pending` → `inventory_reserved` → `payment_authorized` → `confirmed`/`cancelled` via choreography, with catalog-derived payment authorization, terminal notifications, operator-only confirm/cancel routes, and the synchronous checkout compatibility boundary preserved. What remains is production hardening.

### Future

- Real payment provider adapter.
- Saga orchestration and dead-letter handling.
- Observability stack, runbooks, and production deployment.

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
| `frontend/` | React/Vite shopper storefront (catalog, cart, checkout, order tracking, operator console) |
| `.github/` | CI and PR templates |

## Documentation index

| Document | Responsibility |
|----------|--------------|
| [PRD.md](./PRD.md) | Vision, problem, personas, journeys, MVP scope, business rules, non-goals, and metrics |
| [DESIGN.md](./DESIGN.md) | Target UX flows, screen inventory, tokens, and states |
| [docs/GLOSSARY.md](./docs/GLOSSARY.md) | Domain terms and event vocabulary |
| [docs/adr/](./docs/adr/) | Architecture Decision Records |

## Contributing

Work is proposed through GitHub issues and tracked in pull requests: a pull request must reference an issue carrying the `status:approved` label and must carry exactly one `type:*` label, both enforced in CI. Keep the change aligned with the foundation documents above.
