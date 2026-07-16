# eventcommerce

A product-quality portfolio project: a modular, event-driven commerce backend that demonstrates clean architecture, bounded contexts, and asynchronous integration.

## Status snapshot

### Now

- Python backend scaffold with `orders`, `inventory`, `payments`, and `notifications` bounded contexts.
- Shared event envelope, idempotency primitives, and transactional outbox models in `backend/app/shared/messaging/`.
- Order state model supports `pending`, `confirmed`, and `cancelled`.
- FastAPI application structure, SQLAlchemy 2 async mappings, and initial API routes exist.
- **Not yet live**: AMQP consumer, outbox worker/scheduler, IAM, catalog, cart, and frontend.

### MVP Target

A full commerce journey on a single event-driven backend:

- IAM as an owned bounded context with JWT registration, login, and role authorization.
- Catalog, cart, checkout, orders, inventory, deterministic simulated payments, and notifications.
- Event choreography backed by the transactional outbox and idempotent consumers.
- The payment provider is a deterministic simulation behind real ports/adapters; no random outcomes as business behavior.

### Future

- Real payment provider adapter.
- Saga orchestration and dead-letter handling.
- Observability stack, runbooks, and a frontend.

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
| `frontend/` | Reserved for future frontend work (currently empty) |
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
