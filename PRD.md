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
| Shopper | Receive order status updates | Sees `pending`, `confirmed`, or `cancelled` with a reason |
| Store Operator | List products, adjust stock, review orders | Catalog and inventory remain consistent across events |
| Store Operator | Inspect payment decisions | Same inputs always produce the same authorization result in the MVP simulation |

## Now

- Python backend scaffold with `orders`, `inventory`, `payments`, and `notifications` bounded contexts.
- Shared event envelope, idempotency primitives, and transactional outbox models in `backend/app/shared/messaging/`.
- Order state model supports `pending`, `confirmed`, and `cancelled`.
- Payment authorization is currently a non-deterministic stub: `random.choice([True, True, True, False])`.
- **Not yet live**: AMQP consumer, outbox worker/scheduler, IAM, catalog, cart, and frontend.

## MVP Target

A full commerce journey on a single event-driven backend:

- **IAM** as an owned bounded context with JWT registration, login, and role authorization.
- **Catalog** and **Cart** contexts for product browsing and purchase collection.
- **Checkout** orchestrating cart, inventory, and payment in one request.
- **Orders** context with the existing `pending`, `confirmed`, `cancelled` state machine.
- **Inventory** context reserving and releasing stock through events.
- **Payments** context behind ports/adapters with a **deterministic simulated provider**.
- **Notifications** context reacting to order events.
- **Event choreography** backed by the transactional outbox and idempotent consumers.

## Future

- Real payment provider adapter.
- Saga orchestration and dead-letter handling.
- Observability stack, runbooks, and a frontend storefront.

## Business Rules

- A checkout can only be submitted when every cart line has available inventory.
- Inventory is reserved before payment authorization is attempted.
- Payment authorization in the MVP must be deterministic: identical inputs always return the same result.
- Order state transitions are `pending` → `confirmed` or `pending` → `cancelled`; no other transitions are allowed.
- Consumers must be idempotent: processing the same event twice must not duplicate side effects.
- JWT tokens carry roles; role authorization is enforced at API boundaries.

## Non-goals

- Real card processing or PCI compliance in the MVP.
- Live AMQP consumer or outbox worker as a current capability.
- Web storefront, mobile app, or public SaaS operations.
- Production-grade observability, SLA guarantees, or multi-region deployment.
- Saga orchestration and dead-letter queues before the payment flow is stable.

## Metrics

- **Order state correctness**: 100% of simulated orders end in a valid terminal state with the expected event sequence.
- **Payment simulation reproducibility**: a fixed input set produces the same authorization result across 100 repeated runs.
- **Consumer idempotency**: replaying the same event batch produces no duplicate inventory or payment records.
- **End-to-end checkout latency**: p95 under 500 ms for the deterministic MVP path in local tests.

## Glossary

Domain terms and event vocabulary are owned by the [Glossary](./docs/GLOSSARY.md). Architecture decisions are recorded in the [Decision Records](./docs/adr/) and summarized in [ARCHITECTURE.md](./ARCHITECTURE.md). Target UX flows live in [DESIGN.md](./DESIGN.md).
