# Exploration: `messaging-runtime-bootstrap`

> **Mode**: read-only investigation. No code, schema, contract, or test changes.
> **Scope source**: orchestrator launch prompt — the documented messaging gap after the delivered synchronous checkout: AMQP consumer/runtime integration, outbox worker/scheduler/lifespan bootstrap, publisher/consumer boundaries, retry/ack/dead-letter behavior, message-handling idempotency, observability, local/test infrastructure, and the smallest end-to-end vertical slice.
> **Trust posture**: claims grounded in the working tree at HEAD `8ff8bae` (main, clean) plus the just-aligned `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md`, `README.md`, `docs/GLOSSARY.md`, ADRs, and delivered checkout code (PRs #46–#57, docs #58). No AMQP runtime is claimed live anywhere below — existing primitives are foundations until wired and exercised.

## 1. Current state (verified against the working tree)

### 1.1 What exists on disk

| Area | Verified state |
|---|---|
| HEAD | `8ff8bae` (`docs: align documentation with delivered checkout state (#58)`), `main` clean. Checkout PRs #46–#57 merged. `checkout-end-to-end` change folder complete under `openspec/changes/`; archive remains blocked by historical Strict TDD evidence — **not touched**. |
| `checkout` context | Delivered: `backend/app/modules/checkout/` — `Checkout` orchestrator (`POST /api/v1/checkout`), request-key idempotency via `ProcessedEventStore.claim()`, writes `OrderConfirmed`/`OrderCancelled` to outbox, best-effort `SendOrderNotification`. Wired in `app.py` with session-override DI. |
| Publisher | `backend/app/shared/messaging/rabbitmq_publisher.py` — `RabbitMQPublisher(amqp_url, exchange_name="order.events")`, aio-pika `connect_robust`, durable TOPIC exchange, `publish(event)` sends `message_id=event.id`, headers `event_type`/`aggregate_id`, JSON body. **Not connected by the app runtime; `delivery_mode` unset (aio-pika default transient); no reconnect/close wiring.** |
| Outbox | `outbox_events` table + `SqlAlchemyOutboxRepository` (`save`, `get_pending(limit=100)`, `mark_published`). `get_pending` filters `status='pending'` ordered by `created_at` — **no `FOR UPDATE SKIP LOCKED` claim, no index on `(status, created_at)`** (initial schema migration only adds the PK). |
| Worker | `OutboxWorker.run_once(batch_size=100)` — poll → `publisher.publish` → `mark_published`. **No scheduler, no lifespan hook, no loop.** Tested with an `AsyncMock` publisher. |
| Idempotency | `ProcessedEventStore` — `is_processed`/`mark_processed` (used by consumer-style use cases), plus `claim`/`complete_with_response`/`fetch_cached`/`release_claim` (used by checkout) over `processed_events` PK `(event_id, consumer_name)`. Advisory-xact-lock claim helper exists. |
| Envelope | `EventEnvelope` (Pydantic, `event_type` literal of 5 events, `correlation_id`, `causation_id`). **The publisher does not emit this envelope** — it serializes the raw outbox payload dict. The outbox row stores no correlation/causation fields. |
| Consumer use cases | `ProcessInventoryReservation` (inventory, idempotent, expects `items`, emits `InventoryReserved`/`InventoryRejected` to outbox) and `ProcessOrderInventoryResult` (orders, idempotent, `reserved`→`order.confirm()` + outbox `OrderConfirmed`; `rejected`→`order.cancel("insufficient_stock")` + outbox `OrderCancelled`). **Both are unwired: `InventoryContainer` is an empty `DeclarativeContainer`; `ProcessOrderInventoryResult` is wired in `OrdersContainer` but nothing invokes it.** |
| Notifications | Only `SendOrderNotification` (called synchronously by checkout). **No idempotent consumer-side handler for terminal events.** |
| Payments | `AuthorizePayment` + `ProcessPaymentFailure` — synchronous only, no consumer handler (payment via events belongs to the five-state lifecycle, a non-goal here). |
| App runtime | `backend/app/app.py` — `create_app()` wires five module containers and routers; **no lifespan, no messaging runtime startup/shutdown.** |
| Config | `Settings` already has `rabbitmq_user/password/host/port/vhost` + computed `rabbitmq_url` (`amqp://…`), defaults `guest/guest@localhost:5672/`. `EVENTCOMMERCE_RABBITMQ_*` env aliases exist. |
| Local infra | `backend/docker-compose.yml` has **rabbitmq (`rabbitmq:3-management-alpine`, ports 5672/15672, healthcheck)** + postgres + backend (backend gets `RABBITMQ_HOST=rabbitmq`). Broker infrastructure is already defined locally — nothing exercises it. |
| Env docs | `backend/.env.example` **omits all `EVENTCOMMERCE_RABBITMQ_*` vars** (only app/DB vars) despite compose and settings using them. |
| CI | `.github/workflows/api-ci.yml` runs ruff, ruff-format, pyrefly, pytest with a **postgres service only — no rabbitmq service**. |
| Migrations | 6 alembic revisions; head `7b8c9d0e1f2a`. `outbox_events` has no polling index; `processed_events` has no `status` index (checkout claim path filters by PK only). |
| OpenSpec | `openspec/config.yaml` **does not exist** (tree has `changes/` and `specs/` only); previous phases ran without it. |
| Observability | Standard `logging` with key=value message style (e.g. `checkout_completed order_id=%s`). Structured JSON logs/correlation IDs remain **Future** per ARCHITECTURE NFRs; recovery/DLQ also **Future**. |

### 1.2 The documented target chain (ADR 0002, GLOSSARY, ARCHITECTURE)

`OrderCreated` → inventory reservation → `InventoryReserved`/`InventoryRejected` → order confirm/cancel → `OrderConfirmed`/`OrderCancelled` → notifications. Every handler in this chain that already exists as an idempotent application use case is listed above; the transport that would drive them does not exist.

## 2. Key gaps discovered (grounded, beyond "no runtime wiring")

| # | Gap | Evidence | Consequence |
|---|---|---|---|
| G1 | **`OrderCreated` outbox payload lacks `items`** | `CreateOrder.execute()` writes `payload={"customer_id": customer_id}` only; `ProcessInventoryReservation.execute(event_id, order_id, items)` requires `items` | A consumer cannot reserve stock from the message alone; the async chain dead-ends at the first hop. |
| G2 | **Sync checkout pollutes the outbox for the async chain** | `Checkout` → `CreateOrder` writes `OrderCreated`; `_confirm_order`/`_cancel_order` write `OrderConfirmed`/`OrderCancelled`; inventory was already reserved synchronously | Once the worker is live, those rows get published; consuming `OrderCreated` would reserve inventory a second time (no `processed_events` row exists for the sync reservation). Correctness hazard, not cosmetic. |
| G3 | **Poison-loop risk on terminal orders** | `ProcessOrderInventoryResult` calls `order.cancel(reason=…)` for `rejected`; `can_transition('confirmed','cancelled')` raises `InvalidStateTransitionError` | A late/replayed `InventoryRejected` for an already-confirmed order fails the handler → nack/requeue forever unless the handler guards on terminal state. |
| G4 | **Worker has no claim mechanism** | `get_pending` = plain `SELECT … LIMIT`; no `FOR UPDATE SKIP LOCKED`; no `(status, created_at)` index | Multiple worker instances (or uvicorn workers) double-publish; polling scans the table. |
| G5 | **Transient broker delivery** | `RabbitMQPublisher.publish` sets no `delivery_mode` (aio-pika default `NOT_PERSISTENT`) | Broker restart loses forwarded events — undermines the whole point of a transactional outbox. |
| G6 | **Consumer handlers have no container home** | `InventoryContainer` is empty; no dispatcher, no event_type → handler mapping anywhere | The wiring surface must be created; where handlers are registered is an open design decision (D1). |
| G7 | **No notification consumer handler** | Only sync `SendOrderNotification` exists | Closing the ADR 0002 chain (`terminal events → notifications`) needs a new idempotent handler. |
| G8 | **Wire format diverges from the canonical envelope** | Publisher sends headers + raw payload; `EventEnvelope` (with correlation/causation) is unused on the wire | Correlation tracing (Future observability) has no carrier today; either extend outbox schema later or keep header-based format (D3). |
| G9 | **CI/`.env.example` don't cover the broker** | api-ci.yml has no rabbitmq service; `.env.example` lacks `EVENTCOMMERCE_RABBITMQ_*` | Tests must not require a live broker by default; broker-backed coverage needs explicit infra. |

## 3. Affected areas (for the recommended slice in §5)

| Path | Why affected |
|---|---|
| `backend/app/app.py` | Gains a lifespan: start/stop messaging runtime (publisher connect/close, outbox scheduler task, consumer loop). |
| `backend/app/shared/messaging/outbox_worker.py` | `run_once` stays; add a scheduled loop (or a new scheduler module) + graceful shutdown; possibly claim-aware `get_pending`. |
| `backend/app/shared/messaging/outbox_repository.py` | `get_pending` may add `FOR UPDATE SKIP LOCKED` (multi-instance safety, G4). |
| `backend/app/shared/messaging/rabbitmq_publisher.py` | `delivery_mode=PERSISTENT` (G5); idempotent `connect` handling on startup failure. |
| `backend/app/shared/messaging/consumer.py` *(new)* | Shared consume loop + ack policy + `event_type` → handler dispatch. |
| `backend/app/modules/orders/application/create_order.py` | Outbox payload gains `items` (G1). |
| `backend/app/modules/inventory/application/process_inventory_reservation.py` | Order-terminal-state guard (G2/G3) + container wiring. |
| `backend/app/modules/orders/application/process_inventory_result.py` | Order-terminal-state guard (G2/G3). |
| `backend/app/modules/inventory/api/container.py` | Empty container gains the `ProcessInventoryReservation` provider. |
| `backend/app/modules/notifications/application/process_order_notification.py` *(new)* | Idempotent handler for `OrderConfirmed`/`OrderCancelled` → `SendOrderNotification` (G7). |
| `backend/app/modules/notifications/api/container.py` | Gains the new handler provider. |
| `backend/alembic/versions/*` *(new migration)* | `outbox_events (status, created_at)` index; optionally `processed_events status` index (G4). |
| `backend/app/tests/…` | New: consumer dispatcher tests, scheduler test, notification handler tests, broker-free chain e2e; updated: `create_order` payload assertions. |
| `.github/workflows/api-ci.yml` | Optional rabbitmq service for the broker-backed integration test (D6). |
| `backend/.env.example` | Add `EVENTCOMMERCE_RABBITMQ_*` vars (G9). |
| Docs (same change, per repo maintenance rules) | `ARCHITECTURE.md` status rows (outbox worker, publisher, consumer), `docs/GLOSSARY.md` consumer-wiring section, `docs/adr/0002-use-choreography.md` status, `README.md` status snapshot. |

## 4. Approaches

### D1 — Consumer runtime shape

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **Shared consume loop + module registry** | `shared/messaging/consumer.py` owns the aio-pika consume loop, prefetch, ack/nack policy, and a handler registry; `app.py` (or a `messaging_runtime.py`) maps `event_type` → handler provider from each module's container. | One place for ack semantics; contexts stay owners of handlers; matches modular-monolith layering. | Registry indirection must be kept explicit. | Medium |
| Per-module consumer loops | Each context runs its own aio-pika consumer and declares its own queues. | No registry; each context fully owns its subscription. | Duplicated consume/ack logic per context; more startup surface; ack policy drifts. | High |
| Global dispatcher with giant if/elif | One module imports all handlers directly. | Fewest files. | Couples shared code to every context; reverse-dependency smell. | Low |

**Recommended**: shared consume loop + explicit registry (module containers provide handlers; the runtime wires them). Queue declarations live with the runtime registration: e.g. `inventory.order_created` bound `OrderCreated`, `orders.inventory_result` bound `InventoryReserved`/`InventoryRejected`, `notifications.order_terminal` bound `OrderConfirmed`/`OrderCancelled`; durable queues, prefetch=1 (one message per transaction).

### D2 — Outbox worker scheduling

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **FastAPI lifespan asyncio task** | `create_app()` lifespan starts an `asyncio` task looping `sleep(poll_interval) → run_once()`; cancel on shutdown. Publisher connects in lifespan, closes on shutdown. | Zero new dependencies; startup/shutdown deterministic; testable by calling the loop body directly. | In-process scheduler dies with the app (fine for a modular monolith MVP); long-poll sleeps keep a worker busy. | Low |
| Separate worker process (`eventcommerce-backend-worker` console script) | New entry point owning the scheduler; app and worker scale independently. | Operational isolation; production-shaped. | New process + deployment surface + compose service; more than the smallest slice needs. | Medium |
| `apscheduler` | Add dependency for cron-like scheduling. | Rich schedule control. | New dependency for a `while True: sleep()` loop; against lean-dependency rule. | Low |

**Recommended**: lifespan asyncio task with a settings-driven `outbox_poll_interval_seconds` / `outbox_batch_size`, graceful cancel, and **publisher startup failure must not crash the API** (log + retry in background; workers already tolerate a downed broker via requeue). A separate worker process stays a documented follow-up.

### D3 — Wire format

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **Header-based (current publisher shape)** | `message_id` + `event_type`/`aggregate_id` headers + JSON payload; consumer reconstructs event context from these. | No schema change; message-level idempotency key = `message_id`; works today. | No correlation/causation on the wire; `EventEnvelope` stays decorative until outbox gains fields. | Low |
| Full `EventEnvelope` on the wire | Add `correlation_id`/`causation_id` columns to `outbox_events`, populate at emission, publish the envelope. | Wire matches the canonical model; correlation tracing (Future) has a carrier. | Schema + every emitter changes; bigger diff; not needed for the smallest slice. | High |

**Recommended**: header-based for this change. Record envelope-fidelity as a follow-up tied to the observability (correlation IDs) work.

### D4 — Sync-checkout / async-chain coexistence (G2, G3)

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **Order-terminal-state guard in consumer handlers** | `ProcessInventoryReservation` and `ProcessOrderInventoryResult` read the order's status (via a read-only orders dependency) and no-op when the order is already terminal. | Correctness preserved with the sync path; `processed_events` still records the skip (idempotent); cross-context read mirrors the precedent checkout already sets (checkout composes other contexts' use cases). | Adds an application-layer cross-context read (bends the strict domain-layer rule, but checkout already sets this precedent). | Medium |
| Stop outbox emission from the sync checkout | Checkout no longer writes `OrderCreated`/`OrderConfirmed`/`OrderCancelled` to the outbox. | No double-processing possible. | Breaks the delivered contract (outbox emission is a documented Now capability of checkout); `POST /orders`-created orders still emit; notifications consumers starve for checkout orders; touches delivered code. | Medium |
| Per-order processed ledger in inventory | New table recording reservations per order; consumer checks it. | Strong invariant. | New table + repository + migration for a case a status guard covers. | High |

**Recommended**: the order-terminal-state guard (first row), with the exact mechanism (repository read vs. application use case) verified in design. This also neutralizes the G3 poison loop (skip when terminal) and G1 can be fixed at the source (payload gains `items`).

### D5 — Ack, retry, dead-letter

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **At-least-once + consumer idempotency** | Handle message and record `processed_events` in one transaction; `ack` after commit; `nack(requeue=True)` on handler failure (rollback first); no attempt counter, no DLQ. | Matches the existing `is_processed`/`mark_processed` primitives; exactly-once effect without broker features; smallest correct behavior. | A permanently-bad message requeues forever (G3 guard prevents the known case); no DLQ (documented **Future** NFR). | Low |
| Reject-after-N via `x-death` | Track delivery count header; `reject` (drop) after N attempts. | Bounds poison messages. | Extra header parsing; still no durable DLQ; NFR defers DLQ. | Low-Medium |
| Dead-letter exchange + queue now | Declare DLX/DLQ, route exhausted messages there. | Production-shaped recovery. | Explicitly **Future** per ARCHITECTURE NFR table; adds topology + tests now. | Medium |

**Recommended**: at-least-once + idempotency, `ack` after commit, `nack(requeue=True)` otherwise, prefetch=1, persistent delivery (G5). DLQ remains Future.

### D6 — Test / local infrastructure

| Option | Description | Pros | Cons | Effort |
|---|---|---|---|---|
| **Broker-free by default + one gated broker integration** | Unit/chain tests mock `aio_pika` (existing pattern: `patch("…aio_pika.connect_robust")`) or drive the dispatcher with a fake incoming-message object; one broker-backed e2e marked (e.g. `@pytest.mark.integration`, skipped when `EVENTCOMMERCE_RABBITMQ_*` unreachable); add rabbitmq service to api-ci.yml so the gated test runs in CI. | Local `pytest` stays green without Docker; real broker exercised in CI and via docker-compose locally. | Two test layers to maintain; CI job gains a service (cheap). | Medium |
| Only mocked tests | No broker anywhere. | Simplest. | The wire path is never exercised end-to-end; exactly what this change is about. | Low |

**Recommended**: broker-free default + gated broker e2e; add the rabbitmq service to `api-ci.yml` and the missing `EVENTCOMMERCE_RABBITMQ_*` vars to `.env.example` (G9).

## 5. Recommended smallest first slice

> **`messaging-runtime-bootstrap` — wire the documented choreography chain end to end (D1-shared + D2-lifespan + D3-headers + D4-guard + D5-at-least-once + D6-both).**
>
> 1. **Emission fix (G1)**: `CreateOrder` outbox payload gains `items`.
> 2. **Runtime bootstrap**: FastAPI lifespan starts (a) publisher `connect` (idempotent, non-fatal on broker down) and (b) an asyncio outbox scheduler task (`run_once` on a settings-driven interval, graceful cancel); publisher sets `delivery_mode=PERSISTENT`; `get_pending` gains `FOR UPDATE SKIP LOCKED`; migration adds `outbox_events(status, created_at)` index.
> 3. **Consumer runtime**: `shared/messaging/consumer.py` — durable queue declarations, prefetch=1, per-message transaction (handle + `processed_events` + commit → `ack`; rollback → `nack(requeue=True)`), registry of `event_type` → handler providers; wired in `app.py` lifespan with handlers from the module containers: `OrderCreated` → `ProcessInventoryReservation`, `InventoryReserved`/`InventoryRejected` → `ProcessOrderInventoryResult`, `OrderConfirmed`/`OrderCancelled` → new `ProcessOrderNotification`.
> 4. **Guards (G2/G3)**: both existing handlers no-op when the order is already terminal (mechanism verified in design).
> 5. **Notification handler (G7)**: idempotent `ProcessOrderNotification` delegating to `SendOrderNotification`; container provider.
> 6. **Tests**: dispatcher tests, scheduler test, updated worker/publisher tests (persistent delivery), notification-handler tests, broker-free chain e2e (`POST /orders`-style: `CreateOrder` → worker `run_once` → dispatcher(`OrderCreated`) → `run_once` → dispatcher(`InventoryReserved`) → assert `confirmed`), plus one gated broker e2e run in CI.
> 7. **Infra/docs (G9)**: rabbitmq service in `api-ci.yml`; `EVENTCOMMERCE_RABBITMQ_*` in `.env.example`; update `ARCHITECTURE.md` status rows, `docs/GLOSSARY.md` consumer-wiring section, ADR 0002 status, `README.md` snapshot — all in the same change per repo maintenance rules.

Explicit non-goals (already given, restated as boundaries): catalog, cart, IAM, frontend, real payment provider, **five-state order lifecycle** (the async path keeps today's `pending → confirmed/cancelled` semantics; `InventoryReserved` → payment-authorization remains the state-machine follow-up), arbitrary refactors. No claims that AMQP is live are introduced anywhere in docs before the runtime ships.

Suggested chain boundaries if the 800-line budget needs slicing (forecast by `sdd-tasks`): **(a)** emission fix + worker/publisher hardening + migration + scheduler/lifespan; **(b)** consumer runtime + guards + notification handler + dispatcher tests; **(c)** gated e2e + CI/env infra + docs realignment.

## 6. Unresolved decisions & dependencies

- **Unresolved (for proposal/design)**: exact guard mechanism for G2/G3 (repository read vs. cross-context use case); queue naming/binding ownership (runtime registry vs. module-owned declarations); broker-down startup policy (log-and-retry vs. fail-fast toggle); whether `get_pending` claim-lock lands in this slice or with multi-instance work.
- **Dependencies**: `aio-pika` already in `pyproject.toml` (no new runtime deps); docker-compose rabbitmq already defined; CI postgres service already present (rabbitmq service is additive).
- **Precedents**: mock-based publisher/worker tests; session-override DI; checkout's cross-context composition (justifies D4 guard); key=value `logging` style (observability stays minimal — structured logs remain Future).

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Slice exceeds the 800-line review budget | High | High — auto-chain | `sdd-tasks` forecasts; suggested chain boundaries in §5; delivery strategy is auto-chain. |
| G2 double-processing ships unnoticed (inventory reserved twice for checkout-created orders) | Medium | High | D4 guard is in the recommended slice; e2e includes a checkout-created-order replay case. |
| G3 poison loop (late `InventoryRejected` on confirmed order) | Medium | Medium | Terminal-state guard + nack policy; test the replayed-terminal case. |
| Multi-instance double-publish after `FOR UPDATE SKIP LOCKED` lands | Low | Medium | Claim in `get_pending`; consumer idempotency absorbs residual duplicates. |
| Lifespan startup crashes the API when the broker is down | Medium | High | Non-fatal connect + background retry; CI without rabbitmq still boots. |
| Docs realignment drifts from delivered reality again | Medium | Low-Medium | Docs update in the same change; GLOSSARY maintenance rules apply. |
| `openspec/config.yaml` missing | Certain | Low | Not blocking; note for `sdd-init`/orchestrator, not fixed here. |
| `checkout-end-to-end` archive remains blocked | Certain | None for this change | Out of scope; not touched. |

## 8. Ready for proposal

**Yes.** The exploration is grounded, the slice is bounded, and the four open decision points (D1–D6 resolutions above) are pre-resolved with recommendations. The orchestrator should tell the user: `propose` is next; the proposal should confirm the D4 guard mechanism and the queue-naming convention, and `sdd-tasks` must forecast the 800-line budget against the §5 chain boundaries.

## 9. Persistence notes

- Written to `openspec/changes/messaging-runtime-bootstrap/exploration.md` and Engram topic `sdd/messaging-runtime-bootstrap/explore` (project: `eventcommerce`, type: `architecture`, `capture_prompt: false`).
- No `state.yaml` created (orchestrator-owned). No code, schema, test, or doc modified.
