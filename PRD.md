# PRD: eventcommerce

A product-quality, event-driven commerce backend portfolio project. It demonstrates clean architecture, bounded contexts, and asynchronous integration without pretending to be a production storefront.

## Vision

Provide a readable, end-to-end commerce reference implementation that can be reviewed, extended, and discussed. The project proves how a small team can model a full buyer journey using bounded contexts, event choreography, and explicit architectural boundaries.

## Problem

Event-driven systems quickly become hard to reason about when vocabulary, ownership, and status are only implicit in code. Stakeholders and contributors need a shared product definition that separates what exists today, what the MVP aims to prove, and what is intentionally future work.

## Personas

- **The Shopper** — a registered user who browses the catalog, adds items to a cart, checks out, and tracks orders. Needs clear, reliable feedback on inventory, payment, and order status.
- **The Store Operator** — a privileged user who manages the catalog, monitors inventory, and confirms or cancels orders. Needs a trusted audit trail and deterministic operational behavior.

## Journeys

| Persona | Journey | Outcome |
|---|---|---|
| Shopper | Register, log in, browse catalog, add to cart, checkout | Order created with reserved inventory and authorized payment |
| Shopper | Receive order status updates | Sees `pending`, `inventory_reserved`, `payment_authorized`, `confirmed`, or `cancelled` with a reason |
| Store Operator | List products, adjust stock, review orders | Catalog and inventory remain consistent across events |
| Store Operator | Inspect payment decisions | Same inputs always produce the same authorization result in the MVP simulation |

## Now

- Modular Python backend in `backend/app/` with `orders`, `inventory`, `payments`, `notifications`, and `checkout` bounded contexts wired with `dependency-injector`.
- Orders HTTP API (`POST /api/v1/orders`, `GET /api/v1/orders/{order_id}`, `GET /api/v1/orders/{order_id}/timeline`) and a synchronous checkout at `POST /api/v1/checkout`.
- Checkout coordinates order creation, inventory reservation, deterministic payment authorization, and order confirmation/cancellation in one request, with durable `Idempotency-Key` handling: a replay returns the cached response, and a reused key with a different payload returns `409`.
- Shared event envelope, event store, and transactional outbox data structures exist; checkout and orders persist `OrderCreated` / `OrderConfirmed` / `OrderCancelled` events.
- Deterministic simulated payment policy (ADR 0005) replaces the former random stub.
- **Not yet live**: AMQP consumer/runtime, outbox scheduler/worker lifespan integration, IAM/JWT/roles, catalog, cart, the five-state order lifecycle, confirm/cancel HTTP routes, and the storefront frontend.

## MVP Target

The remaining journey on a single event-driven backend. Checkout, deterministic simulated payments, and the shared event/outbox/idempotency primitives are already delivered (see [Now](#now)); the following close out the MVP:

- **IAM** as an owned bounded context with JWT registration, login, and role authorization.
- **Catalog** and **Cart** contexts for product browsing and purchase collection.
- **Orders** reaching the full five-state lifecycle (`pending`, `inventory_reserved`, `payment_authorized`, `confirmed`, `cancelled`) driven by event choreography.
- **Inventory** reserving and releasing stock through events.
- **Notifications** reacting to order events.
- **Event choreography** backed by the transactional outbox and idempotent consumers.

## Future

- Real payment provider adapter.
- Saga orchestration and dead-letter handling.
- Observability stack, runbooks, and a frontend storefront.

## Business Rules

- A checkout can only be submitted when every cart line has available inventory. (Now)
- Inventory is reserved before payment authorization is attempted. (Now)
- Payment authorization must be deterministic: identical inputs always return the same result. (Now)
- Order status transitions in the current synchronous checkout are `pending` → `{confirmed, cancelled}`, with idempotent self-transitions on terminal states. (Now)
- MVP Target — five-state lifecycle: order state transitions become `pending` → `{inventory_reserved, cancelled}`, `inventory_reserved` → `{payment_authorized, cancelled}`, and `payment_authorized` → `{confirmed, cancelled}`; no other transitions are allowed.
- Consumers must be idempotent: processing the same event twice must not duplicate side effects. (Now for the checkout path; wired consumers are MVP Target)
- JWT tokens carry roles; role authorization is enforced at API boundaries. (MVP Target)

## Non-goals

- Real card processing or PCI compliance in the MVP.
- Live AMQP consumer or outbox worker as a current capability.
- Web storefront, mobile app, or public SaaS operations.
- Production-grade observability, SLA guarantees, or multi-region deployment.
- Saga orchestration and dead-letter queues before the payment flow is stable.

## Metrics

- **Order state correctness** (Now): 100% of simulated orders end in a valid terminal state following the transitions in `backend/app/modules/orders/domain/services.py` (`pending` → `{confirmed, cancelled}`).
- **Payment simulation reproducibility** (Now): a fixed input set produces the same authorization result across repeated runs.
- **Consumer idempotency** (Now for the checkout path): replaying an `Idempotency-Key` produces no duplicate order, inventory, or payment records; wired AMQP-consumer replay is MVP Target.
- **End-to-end checkout latency** (MVP Target): p95 under 500 ms for the deterministic MVP path in local tests; benchmark evidence is not yet produced.

## Glossary

Domain terms and event vocabulary are owned by the [Glossary](./docs/GLOSSARY.md). Architecture decisions are recorded in the [Decision Records](./docs/adr/) and summarized in [ARCHITECTURE.md](./ARCHITECTURE.md). Target UX flows live in [DESIGN.md](./DESIGN.md).
