# eventcommerce

A product-quality portfolio project: a modular, event-driven commerce backend that demonstrates clean architecture, bounded contexts, and asynchronous integration.

## Status snapshot

### Now

- Modular Python backend in `backend/app/` with `orders`, `inventory`, `payments`, `notifications`, and `checkout` bounded contexts, wired through `dependency-injector` per-module containers.
- Orders HTTP API: `POST /api/v1/orders`, `GET /api/v1/orders/{order_id}`, and `GET /api/v1/orders/{order_id}/timeline`.
- Synchronous checkout at `POST /api/v1/checkout`: creates the order, locks and reserves inventory (row-level `FOR UPDATE`), authorizes payment with a deterministic simulated policy (ADR 0005), and reaches `confirmed` or `cancelled` in one request.
- Durable idempotency and response cache: `Idempotency-Key` claims with replay detection and `409` on payload mismatch, backed by the `processed_events` table.
- Shared event envelope, event store (`domain_events`), and transactional outbox (`outbox_events`) data structures; checkout and orders persist events to them.
- Quality checks in CI: `ruff check`, `ruff format --check`, `pyrefly check`, and `pytest`.
- **Not yet live**: AMQP consumer/runtime, outbox scheduler/worker lifespan integration, IAM/JWT/roles, catalog, cart, the five-state order lifecycle, confirm/cancel HTTP routes, and the storefront frontend. The RabbitMQ publisher and outbox worker modules exist but are not wired into the running app.

### MVP Target

The remaining commerce journey on a single event-driven backend:

- IAM as an owned bounded context with JWT registration, login, and role authorization.
- Catalog and cart contexts for product browsing and purchase collection.
- Live event choreography: wire the AMQP consumer and outbox worker so contexts react to published events instead of the synchronous checkout path.
- The full five-state order lifecycle (`pending` → `inventory_reserved` → `payment_authorized` → `confirmed`/`cancelled`) and confirm/cancel HTTP routes.

### Future

- Real payment provider adapter.
- Saga orchestration and dead-letter handling.
- Observability stack, runbooks, and a storefront frontend.

## Five-minute path

1. Read the [Product Requirements](./PRD.md) for the vision, personas, and MVP scope.
2. Read [ARCHITECTURE.md](./ARCHITECTURE.md) for bounded contexts, patterns, and current implementation status, and [DESIGN.md](./DESIGN.md) for UX flows and component states.
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
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Topology, bounded contexts, patterns, NFRs, current implementation status, and ADR index |
| [DESIGN.md](./DESIGN.md) | Target UX flows, screen inventory, tokens, and states |
| [docs/GLOSSARY.md](./docs/GLOSSARY.md) | Domain terms and event vocabulary |
| [docs/adr/](./docs/adr/) | Architecture Decision Records |

## Contributing

Work is planned and tracked through SDD changes under `openspec/changes/`. Before proposing a code change, open or review the relevant SDD change and make sure your work aligns with the current foundation documents.
