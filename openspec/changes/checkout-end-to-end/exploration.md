# Exploration: `checkout-end-to-end`

> **Mode**: read-only investigation. No code, schema, or contract changes.
> **Scope source**: orchestrator launch prompt — "the next vertical slice recommended by current product docs and implementation: an end-to-end checkout capability connecting catalog/cart/order creation, inventory reservation, deterministic simulated payment, order confirmation/cancellation, and notification intent."
> **Trust posture**: the orchestrator warned that `sdd-init/eventcommerce` is historically stale and that PRD/ARCHITECTURE/DESIGN/ADRs must be verified against current code. The doc-vs-code drift is material and is listed explicitly under **Stale documentation flags**.

## 1. Current state (verified against the working tree on `main`)

### 1.1 What is actually implemented

Working tree verified on commit `171528e` (HEAD of `main`). Verified facts:

| Area | Verified state |
|---|---|
| Branch | `main`, clean |
| Recent merge | `c466609 feat(backend): deliver Phase 1 commerce workflow (#20)` |
| Tests | `uv run pytest --collect-only` collects **105**; 50 are integration tests that need a live PostgreSQL (refused at `127.0.0.1:5432`), 55 are unit/in-memory and pass locally |
| Backend code root | `backend/app/modules/{orders,inventory,payments,notifications}/` plus `backend/app/shared/{config,db,events,messaging}/` |
| Shared infrastructure | `EventEnvelope` (Pydantic with `Literal[...]` event vocabulary), `SqlAlchemyEventRepository` + `domain_events` table, `SqlAlchemyOutboxRepository` + `outbox_events` table, `ProcessedEventStore` + `processed_events` table, `OutboxWorker.run_once()`, `RabbitMQPublisher` (aio-pika, `order.events` topic exchange) — **all on disk** |
| `orders` HTTP API | `POST /api/v1/orders`, `GET /api/v1/orders/{id}`, `GET /api/v1/orders/{id}/timeline` (real routes; session-override DI in place) |
| `inventory` / `payments` / `notifications` HTTP API | Only `GET /_health` (no business routes) |
| DI containers | `OrdersContainer` is real and wired in `app.py`; `InventoryContainer`, `PaymentsContainer`, `NotificationsContainer` are empty `DeclarativeContainer` shells |
| `OrdersContainer` providers | `order_repo`, `event_repo`, `outbox_repo`, `create_order`, `get_order`, `get_order_timeline` — **does not wire `ConfirmOrder`, `CancelOrder`, `ProcessOrderInventoryResult`** even though those use cases exist |
| Outbox worker scheduler / AMQP consumer | **Not present anywhere** — `OutboxWorker.run_once()` is callable but nothing schedules it; no `aio-pika` consumer, no consumer dispatcher, no FastAPI lifespan integration |
| `frontend/` | Does not exist on disk (only mentioned in `.gitignore`) |
| Docker compose | Exists at `backend/docker-compose.yml` (postgres + rabbitmq + backend); not used by the integration test suite |
| Alembic | 4 migrations, head `4d6e7a8b9c0f`; metadata includes `orders`, `order_items`, `inventory`, `outbox_events`, `processed_events`, `domain_events`, `payments`, `notifications` |

### 1.2 Existing use cases and where they live

| Use case | File | Wired into HTTP? | Event vocabulary used |
|---|---|---|---|
| `CreateOrder` | `backend/app/modules/orders/application/create_order.py` | Yes (`POST /api/v1/orders`) | Persists `OrderCreated` to domain_events **and** outbox |
| `GetOrder` | `…/application/get_order.py` | Yes (`GET /api/v1/orders/{id}`) | — |
| `GetOrderTimeline` | `…/application/get_order_timeline.py` | Yes (`GET /api/v1/orders/{id}/timeline`) | Reads `domain_events` |
| `ConfirmOrder` | `…/application/confirm_order.py` | **No** | Does **not** emit any event |
| `CancelOrder` | `…/application/cancel_order.py` | **No** (no `/cancel` route) | Does **not** emit any event; silently no-ops when order is missing |
| `ProcessOrderInventoryResult` | `…/application/process_inventory_result.py` | **No** | Idempotent; emits `InventoryReserved`/`InventoryRejected` to domain_events and `OrderConfirmed`/`OrderCancelled` to outbox |
| `ReserveInventory` | `…/application/reserve_inventory.py` | No (no `/inventory` route) | — |
| `ReleaseInventory` | `…/application/release_inventory.py` | No | — |
| `ProcessInventoryReservation` | `…/application/process_inventory_reservation.py` | No (intended AMQP consumer) | Idempotent; emits `InventoryReserved`/`InventoryRejected` to outbox |
| `AuthorizePayment` | `…/application/authorize_payment.py` | No | Still uses `random.choice([True, True, True, False])`; ADR 0005 deterministic policy **not** implemented |
| `ProcessPaymentFailure` | `…/application/process_payment_failure.py` | No | Body is `pass` — stub |
| `SendOrderNotification` | `…/application/send_order_notification.py` | No | — |

### 1.3 Order state machine (the actual one in code)

`backend/app/modules/orders/domain/services.py` is the **Phase 1** simplification:

```python
_PHASE1_ALLOWED: dict[str, set[str]] = {
    "pending": {"pending", "confirmed", "cancelled"},
    "confirmed": {"confirmed"},
    "cancelled": {"cancelled"},
}
```

`Order.confirm()` and `Order.cancel()` consult `can_transition` against the table above. There are **no `inventory_reserved` or `payment_authorized` states** in the implemented state machine. The richer 5-state diagram in `PRD.md` §Order status and in `ARCHITECTURE.md` `stateDiagram-v2` is **not** in code; the `Order` dataclass only ever holds `status ∈ {"pending","confirmed","cancelled"}`.

`ProcessOrderInventoryResult` calls `order.confirm()` when the result is `"reserved"` — that is, the Phase 1 implementation goes `pending → confirmed` on inventory success **without** ever reserving payment. The current `test_core_flow.py` "happy path" ends with the order in `confirmed` after inventory reservation and **no payment step**.

### 1.4 What the integration test actually exercises

`backend/app/tests/test_core_flow.py` is the closest thing to an end-to-end test today. It calls the use cases directly (no AMQP, no FastAPI), in three scenarios:

1. `test_happy_path_confirm_order` — `CreateOrder → ProcessInventoryReservation → ProcessOrderInventoryResult("reserved")`; asserts `order.status == "confirmed"` and `inventory.reserved_quantity == 2`. **No payment.**
2. `test_insufficient_stock_cancels_order` — same chain with `"rejected"`; asserts `cancelled` and `cancel_reason == "insufficient_stock"`. **No payment.**
3. `test_idempotency_no_duplicate_inventory` — same `event_id` replayed twice; asserts reserved quantity stays at 2.

So the existing end-to-end test **stops at the inventory boundary**. There is no test that exercises `AuthorizePayment` against the order pipeline, and no test that emits a `PaymentAuthorized`/`OrderConfirmed` round trip.

### 1.5 What's not on disk

- `iam/` bounded context (no folder, no `auth` route).
- `catalog/` bounded context (no folder, no `/catalog` route, no Product entity).
- `cart/` bounded context (no folder, no `/cart` route, no Cart entity).
- `checkout/` bounded context (no folder, no `/checkout` route, no `Checkout` use case or orchestrator).
- AMQP consumer — no `aio_pika.connect_robust`-backed dispatcher; no consumer-side mapping from `event_type` to handler.
- Outbox scheduler — no `asyncio` task, no `apscheduler`, no separate worker process wired up in `main.py` or `app.py` lifespan.
- `app.py` lifespan integration — only routes are registered; no startup/shutdown hooks.
- `backend/app/api/v1/router.py` — directory is empty (only `__pycache__`); module routers are mounted directly from `app.py` via `app.include_router(...)`.
- `frontend/` — does not exist.
- `orders/infrastructure/repositories/sqlalchemy_repository.py` — a leftover stub (`get_by_id` returns `None`, `save` is `pass`); production code imports the real implementation at `infrastructure/sqlalchemy_repository.py`. Confusing duplicate that should be deleted in a follow-up.

### 1.6 Stale documentation flags (per orchestrator warning)

| Document | Stale claim | Verified current truth |
|---|---|---|
| `README.md` "Now" | "each module currently exposes only a `GET /_health` route" | Orders exposes `POST /api/v1/orders`, `GET /api/v1/orders/{id}`, `GET /api/v1/orders/{id}/timeline` |
| `README.md` "Now" | "No shared event envelope, transactional outbox, idempotency store, RabbitMQ publisher, or `dependency-injector` containers exist" | All of these exist under `backend/app/shared/{events,messaging}/` and `backend/app/modules/orders/api/container.py` |
| `README.md` "Now" | "Order aggregate … supports `pending`, `inventory_reserved`, `payment_authorized`, `confirmed`, and `cancelled`" | Code only supports `pending`/`confirmed`/`cancelled`; the richer 5-state machine is **target**, not Now |
| `README.md` "Now" | "Not yet live: AMQP consumer, outbox worker/scheduler, IAM, catalog, cart, checkout, shared messaging, and frontend" | Shared messaging **is** live; AMQP consumer / outbox scheduler / IAM / catalog / cart / checkout / frontend are correctly listed as not live |
| `PRD.md` "Now" | Same as README "Now" — health-only routes, no shared infra, 5-state order, payment is a random stub | Same corrections: orders has real routes; shared infra is live; state machine is the 3-state Phase 1 simplification; payment random stub is **correct** |
| `PRD.md` "MVP Target" / "Business Rules" | "Order state transitions are `pending → {inventory_reserved, cancelled}`, `inventory_reserved → {payment_authorized, cancelled}`, `payment_authorized → {confirmed, cancelled}`" | These transitions are not in code today |
| `PRD.md` "MVP Target" | "A checkout can only be submitted when every cart line has available inventory" | No checkout entry point exists |
| `ARCHITECTURE.md` status matrix | Almost every row tagged "MVP Target / target" with "(no code in published tree)" | Outbox, envelope, idempotency, RabbitMQ publisher, dependency-injector containers are all on disk |
| `ARCHITECTURE.md` "Now" | "Each bounded context … only `GET /_health` exposed" | Orders has real routes |
| `ARCHITECTURE.md` "Now" | "Payment authorization is currently a non-deterministic stub: `random.choice([True, True, True, False])`" | **Correct** — `AuthorizePayment` still has the random stub |
| `docs/adr/0001-use-shared-event-store.md` | "Status: Accepted (MVP Target)" | Implementation exists; status should be "Accepted (current implementation)" |
| `docs/adr/0002-use-choreography.md` | "Status: Accepted (MVP Target)" | Choreography is wired in code paths but the AMQP transport is not bootstrapped; honest status is "Partially implemented" |
| `docs/adr/0003-use-dependency-injector.md` | "Status: Accepted (MVP Target)" | `OrdersContainer` is live; the other three are empty shells. Honest status is "Partially implemented" |
| `docs/adr/0004-own-iam-context.md` | "Status: Accepted (MVP Target)" | No code. Status is correct |
| `docs/adr/0005-use-deterministic-simulated-payments.md` | "Status: Accepted (MVP Target)" | Still random. Status is correct |
| `docs/GLOSSARY.md` "Current events" | `InventoryReserved` produced by `inventory`; `PaymentAuthorized` produced by `payments`; `OrderNotificationSent` produced by `notifications` | No per-module `events.py` exists in those modules; the events are emitted as string literals by the use cases and captured by the shared envelope. The vocabulary matches `EventEnvelope` `Literal[...]` (which is the binding source) |
| `DESIGN.md` | Header says "no frontend implementation" | Still accurate |
| `backend/README.md` | Documents `api/routes/v1/` and `api/schemas/` micro-folders that no longer exist after the refactor | `OrdersContainer` and the routers live at `api/routes.py` and `api/schemas.py` (flat). Stale |

> A `reconstruct-project-foundation`-class follow-up is implied to realign these docs after Phase 1; that is **out of scope** for this change but is a real piece of debt to flag.

## 2. Affected areas (for the recommended first slice in §4)

These are the files and surfaces that the smallest coherent checkout slice will touch. They are listed here as evidence anchors; the proposal/design phases will own the actual diffs.

| Path | Why it is affected |
|---|---|
| `backend/app/modules/orders/domain/services.py` | State machine is the 3-state Phase 1; the checkout flow needs `inventory_reserved` and `payment_authorized`. The recommended slice does **not** change the state machine — it threads payment authorization as a synchronous use case that calls `Order.confirm()` only when payment is authorized. State-machine expansion is a follow-up. |
| `backend/app/modules/orders/domain/entities.py` | `Order` already exposes `confirm()` / `cancel()`. No change needed for the recommended slice. |
| `backend/app/modules/orders/application/process_inventory_result.py` | Already idempotent; will become the inner step of the synchronous checkout orchestrator. |
| `backend/app/modules/orders/api/container.py` | Needs to expose `ProcessOrderInventoryResult`, `ConfirmOrder`, `CancelOrder` so the orchestrator can compose them. Currently only `CreateOrder`, `GetOrder`, `GetOrderTimeline` are wired. |
| `backend/app/modules/orders/api/routes.py` | Needs the checkout route to live here (or in a new `backend/app/modules/checkout/api/routes.py`). |
| `backend/app/modules/payments/application/authorize_payment.py` | Replace `random.choice` with a deterministic policy keyed on `(order_id, amount, currency)` (ADR 0005). Add an in-process policy registry so tests can inject a fixed policy and the canonical policy is "always true below a threshold, always false above" or a hash-based stable function. |
| `backend/app/modules/payments/application/process_payment_failure.py` | Replace `pass` with the actual implementation: mark payment as `failed`, persist `PaymentFailed` to domain_events, emit `OrderCancelled` to outbox (or rely on the orchestrator to do that — see §3.2 for a decision). |
| `backend/app/modules/inventory/api/container.py` / `routes.py` | Empty; will need a route to seed inventory (e.g. `PUT /api/v1/inventory/{product_id}`) for the integration test. Or the test can seed via a fixture, in which case no route is needed. |
| `backend/app/modules/notifications/application/send_order_notification.py` | Real; the orchestrator will invoke it after `Order.confirm()` and on `Order.cancel(reason=...)`. |
| `backend/app/modules/checkout/` (new) | A new bounded context for the orchestrator. Or, more conservative, add `Checkout` use case under `orders` — see §3.1. |
| `backend/app/modules/orders/api/schemas.py` | Needs `CheckoutRequest` and `CheckoutResponse` Pydantic schemas. |
| `backend/app/app.py` | May need to register the checkout router and a `PaymentsContainer` provider (currently empty). |
| `backend/app/tests/test_core_flow.py` | Will be replaced/extended by a new `test_checkout_end_to_end.py` that covers happy path, payment rejected, inventory insufficient, idempotency on retry. |
| `docs/GLOSSARY.md` | If the slice introduces a new event type (e.g. `PaymentFailed`), it must be appended to the canonical vocabulary. For the recommended slice, no new event types are required — `InventoryReserved`/`InventoryRejected`/`OrderConfirmed`/`OrderCancelled` already exist. |
| `docs/adr/0005-use-deterministic-simulated-payments.md` | Will move from "Accepted (MVP Target)" to "Accepted (current implementation)" once the random stub is replaced. The recommended slice includes this update. |

## 3. Approaches

### 3.1 Where the orchestrator lives

Three options for who owns the checkout flow:

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **A1 — New `checkout` bounded context** | New `backend/app/modules/checkout/` with `domain/`, `application/`, `infrastructure/`, `api/`. Orchestrator use case `Checkout` composes `CreateOrder` → `ReserveInventory` → `AuthorizePayment` → `ConfirmOrder` (or `CancelOrder`) → `SendOrderNotification`. | Matches the PRD/ARCHITECTURE vocabulary; clearly its own aggregate; easy to test in isolation. | New module boilerplate (container, schemas, router, __init__ files); the orchestrator is the only use case, so the boilerplate is mostly empty. | Low–Medium |
| **A2 — `Checkout` use case inside `orders`** | A new application use case `Checkout` in `backend/app/modules/orders/application/checkout.py` that takes a cart and orchestrates the other use cases via their existing repositories. | Minimal new files; "orders" is already the home of orchestration intent in the current code; no new container needed if the existing `OrdersContainer` is extended. | Cross-module dependencies (orders depending on inventory + payments + notifications) violate the domain layer purity rule that the current layering enforces. Would need an "application/orchestration" layer or a deliberate exception. | Low |
| **A3 — `Checkout` use case inside a new `application/orchestration/`** | A separate "process manager" directory that is allowed to import from any module. | Honest about cross-cutting responsibility; doesn't bloat `orders`; doesn't pretend to be a new bounded context. | Introduces a fifth directory that's not a bounded context; reviewers will question whether it earns its place. | Low |

**Recommended**: **A1** for clarity and to match the PRD's `checkout` bounded context. A2/A3 are documented for the proposal phase to weigh against A1.

### 3.2 Deterministic payment policy options

ADR 0005 mandates deterministic simulated payments. Options for what the policy actually is:

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **P1 — Always-approve below a per-currency threshold, otherwise reject** | Trivial, transparent, easy to demonstrate in a CLI | Zero magic; easy to explain in tests; deterministic | Less interesting demo; not a useful "reproducible simulation" for stress | Trivial |
| **P2 — Stable hash-based policy** | `approved = sha256(f"{order_id}\|{amount}\|{currency}").digest()[0] < threshold` | Truly deterministic per (order_id, amount, currency); matches the ADR wording exactly; no random state in tests | Requires explaining hashing in the demo; subtle off-by-one in test selection | Low |
| **P3 — Per-currency rule table** | Configurable dict: `{"USD": {"approve_below": 1000}, "EUR": {"approve_below": 900}}` | Configurable; per-currency behavior; easy to test | Adds config surface; needs an env var loader | Low |
| **P4 — Seeded random with a fixed default seed** | `random.Random(seed).choice([True]*3 + [False])` with a seed derived from the inputs | Drop-in replacement of the current stub; deterministic by construction | Still feels like the old stub; ADR 0005 wording prefers "same inputs always return the same result" — this satisfies it but reviewers may push back | Trivial |

**Recommended**: **P2**. It is the closest to the ADR 0005 spirit and is one tiny function. P3 is a close second and is the natural extension if a real "configuration" feature is added later.

### 3.3 Synchronous vs event-driven orchestration

| Approach | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **B1 — Synchronous orchestrator (single DB transaction)** | One HTTP call → `Checkout` use case → all inner steps in one request. Idempotency on `idempotency_key` from the request. Outbox rows are still written so the AMQP path can take over later. | Smallest reviewable diff; one route; one use case; one integration test; the AMQP wiring is a follow-up. | Not event-driven; doesn't exercise the consumer side; reviewers will ask "why not AMQP?". | Medium |
| **B2 — Event-driven (AMQP) orchestrator** | Outbox + worker + AMQP consumer + dispatcher + handler mapping. End-to-end test needs a real RabbitMQ. | Matches the long-term architecture; exercises outbox + RabbitMQ + idempotency in one go. | Larger review (multiple new files: consumer, dispatcher, worker scheduler, lifespan hook, integration test with broker). Cannot be merged into the current `OrdersContainer` cleanly because there is no consumer wiring. | High |
| **B3 — Synchronous orchestrator now, AMQP swap-in as a follow-up** | Same as B1, with the orchestrator designed so the inner steps are invokable individually (so the AMQP consumer in a follow-up change can call `ProcessInventoryReservation` and `ProcessOrderInventoryResult` instead of the orchestrator). | Ships a working end-to-end demo in one PR; the AMQP follow-up is a refactor, not a rewrite; preserves the choreography as the long-term path. | Slightly more design work now (to keep the inner use cases callable individually). | Medium |

**Recommended**: **B3** as the smallest coherent MVP slice. B1 if the proposal phase prefers even smaller. B2 is a separate change that comes after B3.

### 3.4 Catalog and cart handling

| Approach | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **C1 — Defer catalog and cart; checkout takes an inline list of `{product_id, quantity}`** | The `CheckoutRequest` is `{customer_id, items: [{product_id, quantity}]}`. No cart persistence. | Smallest slice; matches the current "orders only" reality; the cart is a future concern. | Doesn't satisfy the PRD's "MVP = catalog + cart + checkout" wording; needs a follow-up change to add cart persistence. | Trivial |
| **C2 — Add a minimal `cart` bounded context with in-memory persistence and a `/cart` route** | Shopper posts to `/cart`, then to `/checkout` with a `cart_id`. | Matches PRD MVP wording; can be evolved to add real persistence. | New module; new container; new tests; reviewer will ask "why not catalog first?". | Medium |
| **C3 — Add catalog + cart before checkout** | Full bounded contexts. | Cleanest alignment with PRD MVP. | Largest first slice; effectively three changes; not "smallest coherent". | High |

**Recommended**: **C1** for the first slice. Catalog and cart as a follow-up change. This is the smallest coherent MVP — the orchestrator still works without a cart because the shopper passes items inline; adding cart persistence is an additive change.

## 4. Recommendation

The **smallest coherent MVP slice** is:

> **`checkout-end-to-end` — synchronous checkout orchestrator (Approach A1 + B3 + C1 + P2).**
> A new `checkout` bounded context that exposes `POST /api/v1/checkout`. The orchestrator runs `CreateOrder → ProcessInventoryReservation → AuthorizePayment (deterministic, P2) → ConfirmOrder` on success, or `CancelOrder` on inventory rejection, and emits a `SendOrderNotification` at the terminal state. Idempotency on a request `Idempotency-Key` header or a server-derived `order_id` (so retries don't double-charge or double-reserve). Outbox rows are still written so the AMQP follow-up can replace the orchestrator's inner calls with `ProcessOrderInventoryResult` consumed from `order.events`.
>
> Within the same change:
> - Replace `random.choice` in `AuthorizePayment` with a stable hash-based policy (ADR 0005).
> - Wire `ConfirmOrder`, `CancelOrder`, `ProcessOrderInventoryResult` into `OrdersContainer` (currently absent).
> - Add a `PaymentsContainer` provider for `AuthorizePayment` and a `ProcessPaymentFailure` use case that actually persists `PaymentFailed` to the `payments` table and emits `OrderCancelled` to the outbox.
> - Update `docs/adr/0005-use-deterministic-simulated-payments.md` from "Accepted (MVP Target)" to "Accepted (current implementation)".
> - Add a new integration test `test_checkout_end_to_end.py` covering: happy path, payment rejected, inventory insufficient, idempotent retry, no-PostgreSQL-required unit test for the deterministic payment policy.
> - Leave the order state machine on the 3-state Phase 1 simplification. The orchestrator's `ConfirmOrder` call is what moves `pending → confirmed`; the richer 5-state machine is a follow-up that requires its own delta spec.

Why this slice:

- **Reviews in 1 PR** (or 2 if the deterministic payment is split out as a self-contained chore). The orchestrator is one new use case; the deterministic payment is one new function; the wiring is a few extra `providers.Factory(...)` lines.
- **Exercises 4 of the 4 existing modules end-to-end** — orders, inventory, payments, notifications. This is the first time the four are connected in a single happy path on a real HTTP call.
- **Preserves the long-term choreography path** — outbox rows are still written, and the inner use cases are still callable individually so the AMQP follow-up is a refactor, not a rewrite.
- **Satisfies the orchestrator's "MVP Target" without forcing the AMQP infra to be ready** — the AMQP transport is the next change, not this one.
- **No catalog, no cart, no IAM** — those are deferred to subsequent changes. The shopper submits items inline; the customer is a `str`; the system is honest about that.

Deferred to subsequent changes (each in its own SDD cycle):

| Follow-up | What it adds |
|---|---|
| `bootstrap-amqp-consumer-and-outbox-scheduler` | AMQP consumer + outbox worker scheduler + lifespan hook + handler mapping. The synchronous orchestrator's inner calls become consumer handlers. |
| `add-catalog-bounded-context` | Products with prices, stock metadata, `GET /api/v1/catalog` route. Lets the deterministic payment policy use a real `amount` per product. |
| `add-cart-bounded-context` | Cart persistence, `POST /api/v1/cart`, `GET /api/v1/cart`, cart merge on login. Lets `POST /api/v1/checkout` accept a `cart_id`. |
| `add-iam-auth` | JWT registration, login, role authorization. Replaces the `customer_id: str` with a real subject. |
| `expand-order-state-machine` | Replace the 3-state simplification with `pending → inventory_reserved → payment_authorized → confirmed \| cancelled` and add an `inventory_reserved → cancelled` compensation. Requires its own delta spec. |
| `realign-stale-documentation` | Update `README.md`, `PRD.md`, `ARCHITECTURE.md`, the 5 ADRs, and `docs/GLOSSARY.md` to match verified current state. This is the same shape as the just-archived `reconstruct-project-foundation` but for the next horizon. |

## 5. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The proposed slice exceeds the 400-line review budget | Medium | High — auto-chain will route to chained PRs | Forecast in `sdd-tasks`; split into "deterministic payment + ADR update" and "checkout orchestrator + tests" |
| `ProcessPaymentFailure` rewrite conflicts with `ProcessOrderInventoryResult`'s "cancelled" path | Medium | Medium — double-cancel / inconsistent `cancel_reason` | Define ownership: the orchestrator calls exactly one terminal transition per order; cancel_reason is set once and only by the orchestrator |
| The Phase 1 state machine silently drops a `payment_authorized` semantic that the orchestrator relies on | Low | Medium | The orchestrator explicitly avoids persisting `payment_authorized`; it only calls `confirm()` after `AuthorizePayment` returns success. The state machine is not changed in this change. |
| `OrdersContainer` extension (adding `ConfirmOrder`, `CancelOrder`, `ProcessOrderInventoryResult`) inadvertently exposes internal use cases over HTTP | Low | Medium | Keep the container wiring internal; expose only the new `/checkout` route. Confirm/Cancel HTTP routes are a follow-up. |
| Stale docs (README/PRD/ARCHITECTURE/ADRs) make reviewers believe capabilities are "future" when they are now live | High | Low–Medium — review friction | The `realign-stale-documentation` change is a recommended follow-up; this exploration explicitly lists the drift so the proposal can call it out |
| `backend/app/modules/orders/infrastructure/repositories/sqlalchemy_repository.py` (the stub) is accidentally imported and breaks a test | Low | Medium | Delete the file in this change; it is dead code. Note in the proposal. |
| The deterministic payment policy is not actually deterministic under `pytest-xdist` or parallel CI due to hash collisions | Very low | Low | P2 uses a stable per-input function (not seeded random), so concurrency is fine |
| Idempotency on the orchestrator isn't wired, leading to double-charge on retry | Medium | High | Wire `Idempotency-Key` header → `processed_events` table via the existing `ProcessedEventStore`. The store is already implemented and tested. |
| `AuthorizePayment`'s random stub is left in place because someone skipped ADR 0005 | Low | Low | The recommended slice includes the deterministic policy; the proposal must list it as an explicit task |
| `app.py` lifespan still doesn't start the outbox worker, so the AMQP transport is dead | High (after this change) | Low for this change, High for the AMQP follow-up | The change does not promise AMQP. The follow-up `bootstrap-amqp-consumer-and-outbox-scheduler` is the place that wires the lifespan. Document this in the proposal. |

## 6. Ready for proposal

**Yes**, with one confirmation needed by the orchestrator: which combination of A1/A2/A3 + P1/P2/P3/P4 + B1/B2/B3 + C1/C2/C3 is preferred? The recommendation above is **A1 + P2 + B3 + C1**. The orchestrator should either accept the recommendation or ask the user to pick.

The orchestrator should also confirm whether `chain_strategy` should be resolved before `sdd-tasks` forecasts work units, per the launch prompt note. The recommended slice is small enough (~600–900 lines including tests and ADR update) that it may fit in a single PR under the 400-line gate, but the deterministic payment + tests will likely push it over. Forecast will resolve this in `sdd-tasks`.

## 7. Persistence notes

- This artifact is written to `openspec/changes/checkout-end-to-end/exploration.md` and to Engram topic `sdd/checkout-end-to-end/explore` (project: `eventcommerce`, type: `architecture`, `capture_prompt: false`).
- No `state.yaml` is created here — the orchestrator owns it.
- No code, no schema, no test, no doc was modified.
