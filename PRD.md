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

- Modular Python backend in `backend/app/` with `orders`, `inventory`, `payments`, `notifications`, `checkout`, `iam`, `catalog`, and `cart` bounded contexts wired with `dependency-injector`.
- Orders HTTP API (`POST /api/v1/orders`, `GET /api/v1/orders/{order_id}`, `GET /api/v1/orders/{order_id}/timeline`) and a synchronous checkout at `POST /api/v1/checkout`.
- Checkout coordinates order creation, inventory reservation, deterministic payment authorization, and order confirmation/cancellation in one request, with durable `Idempotency-Key` handling: a replay returns the cached response, and a reused key with a different payload returns `409`.
- Shared event envelope, event store, and transactional outbox data structures exist; checkout and orders persist `OrderCreated` / `OrderConfirmed` / `OrderCancelled` events.
- Deterministic simulated payment policy (ADR 0005) replaces the former random stub.
- Messaging runtime wired into the app lifespan (`backend/app/messaging_runtime.py`, started/stopped by `backend/app/app.py`): outbox scheduler, RabbitMQ publisher, and AMQP consumer with three durable queues; live broker delivery requires RabbitMQ — default suite proves the chain broker-free (`backend/app/tests/runtime/test_chain_e2e.py`), gated CI proves it against a real broker.
- IAM bounded context (`backend/app/modules/iam/`): `POST /api/v1/iam/register` (shopper-only, `201`/`409`), `POST /api/v1/iam/login` (30-minute HS256 access JWT, generic `401`), and `GET /api/v1/iam/me` (bearer, `200`/`401`); commerce reads/writes enforce owner-or-operator access from the JWT subject.
- Catalog bounded context (`backend/app/modules/catalog/`): public `GET /api/v1/catalog` (active-only browse) and `GET /api/v1/catalog/{product_id}` (detail; missing and inactive share one `404`), plus operator `POST /api/v1/catalog` / `PATCH /api/v1/catalog/{product_id}` product management. Catalog creation seeds an inventory row at zero stock; operators adjust stock via `POST /api/v1/inventory/{product_id}/adjust`.
- Cart bounded context (`backend/app/modules/cart/`): `GET /api/v1/cart` (lazily created), `POST /api/v1/cart/items`, `PATCH` / `DELETE /api/v1/cart/items/{product_id}` — one persisted cart per authenticated shopper, owner-scoped by the JWT subject, with live subtotal from active catalog prices.
- Checkout accepts either the inline `{items, amount, currency}` shape or an optional `cart_id` alone, deriving lines, amount, and currency from authoritative catalog pricing; the JWT subject stays authoritative for ownership.
- **Not yet**: the five-state order lifecycle, confirm/cancel HTTP routes, and the storefront frontend.

## MVP Target

The remaining journey on a single event-driven backend. Checkout (inline and `cart_id` shapes), deterministic simulated payments, catalog browse/manage, owner-scoped carts, the shared event/outbox/idempotency primitives, IAM (register/login/me with shopper-only registration, 30-minute access JWT, and owner-or-operator commerce protection), and the messaging runtime (outbox scheduler + RabbitMQ publisher + AMQP consumer wired into the app lifespan; live delivery requires RabbitMQ) are already delivered (see [Now](#now)); the following close out the MVP:

- **Orders** reaching the full five-state lifecycle (`pending`, `inventory_reserved`, `payment_authorized`, `confirmed`, `cancelled`) driven by event choreography (runtime already wired; intermediate states not yet reachable).
- **Inventory** reserving and releasing stock across the five-state lifecycle (single-event reservation/result reaction already wired).
- **Notifications** reacting to order events across the five-state lifecycle (terminal `OrderConfirmed`/`OrderCancelled` reaction already wired).

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
- Consumers must be idempotent: processing the same event twice must not duplicate side effects. (Now: checkout path and wired AMQP handlers commit handler + `processed_events` in one per-message transaction; live delivery requires RabbitMQ)
- JWT tokens carry roles; role authorization is enforced at API boundaries. (Now: 30-minute access JWT; registration is shopper-only; commerce reads/writes enforce owner-or-operator from the JWT subject)

## Non-goals

- Real card processing or PCI compliance in the MVP.
- Production deployment/operations of the AMQP runtime (wired runtime delivered; live delivery requires RabbitMQ; gated CI proves integration; no production SLA/ops, DLQ, saga, observability, or payment-consumer claim).
- Web storefront, mobile app, or public SaaS operations.
- Production-grade observability, SLA guarantees, or multi-region deployment.
- Saga orchestration and dead-letter queues before the payment flow is stable.
- IAM abuse controls and production readiness: no rate limiting on register/login, no refresh-token rotation, and no production secret-management or hardening claim.

## Metrics

- **Order state correctness** (Now): 100% of simulated orders end in a valid terminal state following the transitions in `backend/app/modules/orders/domain/services.py` (`pending` → `{confirmed, cancelled}`).
- **Payment simulation reproducibility** (Now): a fixed input set produces the same authorization result across repeated runs.
- **Consumer idempotency** (Now: checkout path and wired AMQP handlers): replaying an `Idempotency-Key` or redelivering a wired event produces no duplicate order, inventory, or payment records; proven broker-free by `backend/app/tests/runtime/test_chain_e2e.py`, live delivery requires RabbitMQ.
- **End-to-end checkout latency** (MVP Target): p95 under 500 ms for the deterministic MVP path in local tests; benchmark evidence is not yet produced.

## Glossary

Domain terms and event vocabulary are owned by the [Glossary](./docs/GLOSSARY.md). Architecture decisions are recorded in the [Decision Records](./docs/adr/). Target UX flows live in [DESIGN.md](./DESIGN.md).
