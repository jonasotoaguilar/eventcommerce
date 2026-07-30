# Exploration: `reconstruct-project-foundation`

> **Scope of this change**: rebuild the project's sources of truth — `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md`, justified ancillary docs, and the root `README.md` — **only**. No code, setup, frontend, GitHub, or backend fixes. Those are downstream SDD changes.
>
> **Mode**: read-only. The branch `feat/phase1-config-di-refactor` is **not** to be modified, reverted, formatted, or cleaned by this exploration.

## Current State

### Repository on disk (verified)

- **Branch checked out**: `feat/phase1-config-di-refactor` with a large pending refactor (micro-folders `entities/`, `errors/`, `events/`, etc. → flat files `entities.py`, `errors.py`, `events.py`, `repository.py`, `services.py`; ORM distributed by module; API versioned per module; renamed `domain/models.py → domain/entities.py`; centralized tests).
- **Root `README.md`**: 1-line placeholder (`# eventcommerce`). All other root docs deleted.
- **`backend/README.md`** (5.4K) still present and **mostly** matches the post-refactor structure, but predates several rounds of changes and is partly stale.
- **No `openspec/`, `sdd/`, or `docs/` directory at the root.** The change folder must be created from scratch.
- **Frontend**: empty (no `frontend/` content). `.gitignore` already excludes `frontend/node_modules/`, `frontend/dist/`, `frontend/.next/`, so the folder is expected but not yet populated.
- **`.atl/skill-registry.md`**: present, dated 2026-07-16, lists available skills including `sdd-*` and `docs-writer`. Useful as cross-reference for sub-agents.
- **`skills-lock.json`**: pins external skills (fastapi-python, sqlalchemy-alembic, rabbitmq-expert, python-patterns, etc.). Worth referencing in the foundation to keep the team honest about which external patterns are available.

### Backend codebase (verified, in-disk, not just git)

**Stack**: Python 3.13+, FastAPI 0.136, SQLAlchemy 2.0 (async, psycopg3), Pydantic Settings 2.x, `dependency-injector` 2.x, `aio-pika` 9.x, Alembic 1.x, `uv` for build.

**Layout** (post-refactor, flat per layer):
```
backend/
  app/
    app.py                       # FastAPI factory; wires module containers
    main.py                      # uvicorn entrypoint
    api/v1/router.py             # global v1 router composing module routers
    modules/
      orders/{api,application,domain,infrastructure}
      inventory/{...}
      payments/{...}
      notifications/{...}
    shared/
      config/  (settings.py with validation_alias for POSTGRES_*, RABBITMQ_*)
      db/      (Base, async session)
      events/  (DomainEvent base, DomainEventModel, EventRepository protocol, SqlAlchemyEventRepository)
      messaging/  (OutboxEventModel, ProcessedEventModel, OutboxRepository, OutboxWorker, RabbitMQPublisher, ProcessedEventStore, EventEnvelope)
  tests/                         # centralized under app/tests/
  alembic/versions/  (2 migrations: initial_schema, replace_order_events_with_shared)
  docker-compose.yml             # postgres + rabbitmq + backend
  Dockerfile, pyproject.toml, uv.lock, .env(.example)
```

### What is real, working, and worth documenting as-is

1. **Modular monolith with DDD/Clean layering per bounded context**: `domain/`, `application/`, `infrastructure/`, `api/` for each of `orders`, `inventory`, `payments`, `notifications`.
2. **Shared event store** (`app/shared/events/`):
   - `DomainEvent` base dataclass with neutral `aggregate_id` (so it is not coupled to `order_id`).
   - `DomainEventModel` ORM (`domain_events` table).
   - `EventRepository` Protocol + `SqlAlchemyEventRepository` implementation.
3. **Transactional outbox** (`app/shared/messaging/`):
   - `OutboxEventModel` + `SqlAlchemyOutboxRepository` (`save`, `get_pending`, `mark_published`).
   - `ProcessedEventModel` + `ProcessedEventStore` (idempotency per consumer).
   - `EventEnvelope` Pydantic model with `Literal["OrderCreated", "InventoryReserved", "InventoryRejected", "OrderConfirmed", "OrderCancelled"]` — **the canonical event type vocabulary is already pinned in code**.
4. **RabbitMQ publisher**: `RabbitMQPublisher` over `aio-pika`, topic exchange `order.events`, persistent, with envelope metadata in headers. **Not yet connected to the FastAPI startup lifecycle.**
5. **Orders module** is the only module with a real API:
   - `POST /api/v1/orders` → `CreateOrder` (writes `Order`, persists `OrderCreated` event store entry, persists outbox row).
   - `GET /api/v1/orders/{order_id}` → `GetOrder`.
   - `GET /api/v1/orders/{order_id}/timeline` → `GetOrderTimeline` from event store.
   - State machine: `pending → {pending, confirmed, cancelled}`, `confirmed → confirmed`, `cancelled → cancelled` (idempotent self-transitions allowed).
   - `ProcessOrderInventoryResult` use case: consumes `InventoryReserved`/`InventoryRejected`, transitions the order, persists the new event store entry, and writes the outbox row for `OrderConfirmed` / `OrderCancelled`.
6. **Alembic**: 2 migrations. Migration `9b69790738e5` already migrated the old per-module `order_events` into the shared `domain_events` table — this is a **historical event**, important to record in the ARCH.
7. **Tests**: centralized under `backend/app/tests/`, ~40 test files. Includes an integration `test_core_flow.py` (happy path, insufficient stock, idempotency) that exercises orders + inventory + outbox + idempotency end-to-end **without AMQP** (use cases called directly).
8. **DI per module** (`dependency-injector`): one global `DeclarativeContainer` per module, wired to a single API router file. Session is per-request via FastAPI dependency with `container.session.override(...)` + `reset_override()` in `finally`. Pattern is consistent.
9. **Settings**: `EVENTCOMMERCE_*` prefix via pydantic-settings, plus atomic `POSTGRES_*` and `RABBITMQ_*` via `validation_alias`. Computed `database_url`, `rabbitmq_url`, `test_database_url`.

### Gaps and "future" (must be documented as **target**, not present)

- **Inventory, payments, notifications modules are not wired to the API surface**:
  - `InventoryContainer`, `PaymentsContainer`, `NotificationsContainer` are `DeclarativeContainer` subclasses with only `wiring_config` — no providers.
  - `routes.py` for each of those three exposes only `GET /_health`.
  - Their use cases (`ReserveInventory`, `ReleaseInventory`, `ProcessInventoryReservation`, `AuthorizePayment`, `ProcessPaymentFailure`, `SendOrderNotification`) are implemented in code but have no HTTP entry point.
- **AMQP consumer is not bootstrapped**: no `aio-pika` consumer, no subscription to `order.events` exchange, no dispatcher that routes `OrderCreated` → `ProcessInventoryReservation`, no `InventoryReserved/Rejected` → `ProcessOrderInventoryResult`. The integration test bypasses AMQP entirely.
- **Outbox worker is not scheduled**: `OutboxWorker.run_once()` exists; nothing in the FastAPI lifespan or a separate process invokes it on an interval.
- **No catalog, no cart, no auth/iam**: not in the codebase. Should be treated as **vertical slices** in the PRD, not MVP.
- **No saga with compensations**: the current flow is a "consumer confirms/cancels the order"; there is no explicit compensation step that releases reserved inventory on payment failure.
- **No DLQ**: no policy for events that fail repeatedly.
- **No frontend** (folder exists in `.gitignore`, no source).
- **No observability stack**: no `structlog`, no OpenTelemetry, no Prometheus, no `/health/ready`, no `/health/live` for dependencies.

### Known broken state (not in this change's scope, but must be acknowledged in the foundation)

- **`backend/app/shared/events/__init__.py` line 4**:
  ```python
  from app.shared.events.sqlalchemy_event_repository import SqlAlchemyEventRepository
  ```
  The file `sqlalchemy_event_repository.py` **does not exist on disk**; the class was renamed/moved to `event_repository.py`. Production code (`OrdersContainer`) imports from the correct path; the broken import is consumed by:
  - `backend/app/tests/shared/events/test_event_repository.py`
  - `backend/app/tests/modules/orders/application/test_create_order.py`
  - `backend/app/tests/modules/orders/application/test_get_order_timeline.py`
  - `backend/app/tests/modules/orders/application/test_process_inventory_result.py`
  The test suite is therefore broken until this is fixed in a follow-up change.
- `backend/README.md` describes the structure correctly in broad strokes but has small drifts (e.g., path wording) that will be re-aligned when `backend/README.md` is touched in a follow-up.

### Prior context available

- `mem_search` and `mem_context` retrieved 1500+ observations across the project, including:
  - `sdd-init/eventcommerce` (id 1451) — project context recorded earlier.
  - `Exploración Fase 1 MVP Core Flow` (id 1470) — earlier exploration, before the current large refactor.
  - Architecture/pattern observations covering: shared event store, `DomainEvent` generalization, per-module DI, ORM distribution, flat `domain/` layout, centralized tests, test fixes.
- The current exploration is **post-refactor**; the earlier one (id 1470) is now partially stale (it described stale `entities/` micro-folders) but its **scope recommendations** (vertical slices, deferring catalog/auth/saga/DLQ) remain directionally valid.

## Affected Areas

For this change (purely documentary, root-level files), the **write** target areas are:

- `PRD.md` (new, at project root) — does not exist.
- `ARCHITECTURE.md` (new, at project root) — does not exist.
- `DESIGN.md` (new, at project root) — does not exist.
- `README.md` (replace the 1-line placeholder) — exists, content is just `# eventcommerce`.
- `docs/` (new) — may host `docs/adr/` for ADRs that the ARCHITECTURE will reference, and other justified supplementary docs.

**Out of scope (will be touched by later SDD changes, not this one):**

- `backend/app/**` — including the broken import, outbox scheduling, AMQP consumer bootstrap, and the empty containers for inventory/payments/notifications.
- `backend/README.md` — to be updated when the backend setup/structure is corrected, not now.
- `backend/pyproject.toml`, `backend/.env.example`, `backend/Dockerfile`, `backend/docker-compose.yml`, `backend/alembic/**`.
- `backend/conftest.py` and any test files.
- `.github/**`, `.gitignore`, `skills-lock.json`, `frontend/**` (empty), `openspec/config.yaml` (only if absolutely required by OpenSpec; otherwise the orchestrator creates it).
- Any tracked/untracked file under `feat/phase1-config-di-refactor` — **not to be reverted, formatted, or otherwise modified**.

## Approaches

### 1. Write the foundation docs as a single monolithic pass in this change

- **Pros**: One round of review; consistent voice; minimum churn.
- **Cons**: A single large PR with thousands of lines across three root docs is hard to review; risk of cross-doc inconsistencies passing unnoticed; very likely to exceed the 400-line review budget.
- **Effort**: Medium-High.

### 2. Split the foundation into sub-changes (`PRD`, then `ARCH`, then `DESIGN`, then `README`)

- **Pros**: Each PR is small, scoped, and reviewable; each doc can be iterated on independently; preserves review focus and aligns with the SDD 400-line budget.
- **Cons**: Four PRs before the codebase is touched; inter-doc cross-references can drift; "foundation" is no longer a single atomic change.
- **Effort**: Low per change, Medium total.

### 3. One change, but each doc is its own deliverable inside it (recommended)

- **Pros**: Keeps "foundation" as one logical change while honoring the 400-line review budget (each doc is a separate work unit, small enough to review). A `sdd-apply` plan with a per-doc task sequence and a per-doc PR is realistic.
- **Cons**: Requires careful sequencing in `tasks.md` to avoid merge conflicts if multiple docs reference each other.
- **Effort**: Medium.

## Recommendation

**Approach 3** (single change, per-doc deliverables, per-doc PR). Justification:

- A foundation *must* be coherent across `PRD` ↔ `ARCH` ↔ `DESIGN` ↔ `README`; splitting them into separate SDD changes invites drift between cross-references (e.g., the event-type vocabulary pinned in `EventEnvelope` is a contract the PRD/ARCH/DESIGN must all agree on).
- But the **400-line review budget per PR is a hard limit** (per `sdd-phase-common.md` Section E). A single mega-PR with all three root docs would crush that budget.
- The compromise is one change that produces four well-scoped files, each in its own work unit and its own PR slice, authored in the order `README.md → PRD.md → ARCHITECTURE.md → DESIGN.md` so cross-references in later docs are stable.
- The proposal phase must include a short **architectural lock-in** section enumerating the in-code contracts that the docs MUST honor: bounded-context names, event-type vocabulary (`OrderCreated`, `InventoryReserved`, `InventoryRejected`, `OrderConfirmed`, `OrderCancelled`), order state machine (`pending|confirmed|cancelled`), entity field names (`Order.id`, `Order.items`, etc.), and stack choices. This prevents the docs from drifting from the code.

Inside this single change, ordering matters:

1. `README.md` (small, points at the other three — author first so cross-links are stable).
2. `PRD.md` (defines MVP scope, no-objetivos, personas, business rules).
3. `ARCHITECTURE.md` (defines the system as it is today, plus the in-flight target shapes that are already encoded in code: event store, outbox, publisher, envelope).
4. `DESIGN.md` (defines the UX layer; many of its sections will be aspirational because the frontend does not exist yet — must be tagged as "target design" not "current design").

## Risks

1. **Documenting aspirational architecture as if it were implemented.** Inventory, payments, and notifications modules have domain + use cases but no real HTTP routes, no AMQP consumer, no outbox worker scheduler. A foundation that describes the full event-driven journey as "current state" will misrepresent the project on day one.
   *Mitigation*: every doc must distinguish **Now** (what is committed to disk) from **Target** (what is being built toward). The proposal must include a "current vs target" table per major area.

2. **PRD without personas or non-goals.** Without personas, the user flows in `DESIGN.md` are guesses. Without explicit non-goals, every conceivable feature (catalog, cart, multi-tenant, i18n, payments provider, etc.) can be argued into scope. The user's framing — "no es un simple servicio de órdenes" — risks bloating MVP into a full storefront.
   *Mitigation*: `PRD.md` must have a **Personas** section with 1–2 concrete roles and a **Non-Goals** section that names what MVP explicitly does NOT include (catalog browsing, cart UI, real payment provider, multi-tenant, i18n, etc.).

3. **Inventing a different event-type vocabulary than the code.** `EventEnvelope` has a `Literal[...]` over five event types. If the PRD/ARCH documents a different or broader set, the docs and the code will diverge on day one.
   *Mitigation*: The proposal must include the canonical event-type list and a "contracts" subsection that lists, for each event, the producer, consumer, and the data class it serializes from. Anything in the docs that is not on that list must be marked as **target**.

4. **Mis-classifying the project type (demo vs product).** "Built to demonstrate/exercise event-driven architecture" is not a commercial MVP. The docs must be honest about the project's nature or the team will build to the wrong definition of done.
   *Mitigation*: `PRD.md` should explicitly state the project's nature ("reference implementation / portfolio / learning vehicle" or "commercial MVP") up front. This is a hard prerequisite that the orchestrator must surface to the user (see `product_questions_for_proposal`).

5. **Backend README goes stale in the opposite direction.** While the root docs are being written, `backend/README.md` will continue to drift from the truth (already slightly stale). Documenting a structure that disagrees with the only existing technical doc is a credibility hit.
   *Mitigation*: The foundation change is out of scope to fix `backend/README.md`, but the ARCHITECTURE.md must explicitly call out "backend/README is being superseded by this document and is scheduled for alignment in change N". The orchestrator must put the backend-README alignment in the follow-up chain.

6. **Outbox/AMQP/Jonas-as-operator assumptions.** The docs risk describing "the outbox publishes reliably" when in fact the publisher/worker/consumer is not bootstrapped. A reader (or a future LLM agent) will assume the contract holds.
   *Mitigation*: `ARCHITECTURE.md` must have a "Current Implementation Status" matrix per architecture decision, with columns: Decision, Status (`implemented` / `partial` / `target`), Code evidence, Doc location. Anything marked `partial` or `target` must not be referenced as if it were live.

7. **Designing UI in `DESIGN.md` without a frontend.** The frontend folder is empty. Any UI artifacts in `DESIGN.md` will be aspirational only.
   *Mitigation*: `DESIGN.md` is explicitly a "target design" document with two clearly labeled columns: "**Now** (code path covered)" vs "**Target** (planned for vertical slices)". Only the Now column is binding.

8. **Broken import in `shared/events/__init__.py` will block anyone running the test suite right after the foundation is merged.** This is not in scope to fix here, but the foundation docs may be the first thing reviewers read, and a failing test suite is a credibility hit.
   *Mitigation*: The orchestrator should sequence the follow-up `fix-shared-events-broken-import-and-bootstrap-messaging` change **before** any other "verify the backend" change. This is reflected in `suggested_followup_changes`.

## verified_findings

> All items below were verified against the working tree (`feat/phase1-config-di-refactor`), the on-disk code, and Engram memory. None is inferred from the user's prior descriptions alone.

1. **Root docs are gone.** `README.md` is a 1-line placeholder; there is no `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md`, or `docs/` at the project root. No `openspec/` or `sdd/` either.
2. **Branch state.** `feat/phase1-config-di-refactor` is checked out with a large uncommitted refactor; dozens of files deleted in git (micro-folders) but the on-disk tree is the post-refactor flat layout. The user explicitly forbade touching this.
3. **Orders API surface is the only real one.** `POST /api/v1/orders`, `GET /api/v1/orders/{order_id}`, `GET /api/v1/orders/{order_id}/timeline`. Verified in `app/api/v1/router.py` and `app/modules/orders/api/routes.py`.
4. **Other modules are stubbed at the API layer.** `inventory`, `payments`, `notifications` each expose only `GET /_health` and have `DeclarativeContainer` subclasses with no providers. Verified.
5. **Event-type vocabulary is pinned in code.** `app/shared/messaging/envelope.py` defines a `Literal["OrderCreated", "InventoryReserved", "InventoryRejected", "OrderConfirmed", "OrderCancelled"]`. Any doc MUST use this exact set.
6. **Order state machine is `pending|confirmed|cancelled` with idempotent self-transitions.** Verified in `app/modules/orders/domain/services.py`.
7. **Event store is shared.** `DomainEvent` (base), `DomainEventModel` (ORM), `EventRepository` (Protocol), `SqlAlchemyEventRepository` (impl). Verified.
8. **Outbox and idempotency are shared.** `OutboxEventModel`, `OutboxEvent` view, `SqlAlchemyOutboxRepository`, `OutboxWorker`, `ProcessedEventModel`, `ProcessedEventStore`. Verified.
9. **RabbitMQ publisher exists** (topic exchange `order.events`, persistent) **but is not connected to the FastAPI startup lifecycle**. No consumer subscribes to the exchange. `OutboxWorker.run_once()` exists with no scheduler. Verified.
10. **Broken import confirmed.** `app/shared/events/__init__.py` line 4 imports `SqlAlchemyEventRepository` from `app.shared.events.sqlalchemy_event_repository`, a file that does not exist. The class lives in `event_repository.py`. Four test files import from the broken path; `OrdersContainer` (production code) imports from the correct path.
11. **Alembic has 2 migrations.** `a14ca47ad70f_initial_schema.py` and `9b69790738e5_replace_order_events_with_shared_domain_events.py` (which migrates data from the old per-module `order_events` into the shared `domain_events` table and drops the old one). Verified.
12. **Tests are centralized** under `backend/app/tests/{modules,shared}/` with coverage across `api/application/domain/infrastructure` per module. `test_core_flow.py` exercises the happy path + insufficient stock + idempotency without AMQP. Verified.
13. **DI pattern is "global container per module, per-request session override".** `OrdersContainer` is a module-level singleton; FastAPI overrides `container.session` for the request lifetime and resets it in `finally`. Verified in `app/app.py` and `app/modules/orders/api/routes.py`.
14. **Frontend is empty.** `frontend/` has no tracked or untracked source files (only present as a path in `.gitignore`).
15. **Engram has 1500+ observations on `eventcommerce`** including `sdd-init/eventcommerce` (id 1451) and an earlier exploration (id 1470) that is partially stale (predates the current refactor). Scope recommendations from id 1470 remain directionally valid.

## product_questions_for_proposal

These are the questions the orchestrator MUST surface to the user **before** the proposal is written. Each one is a fork with material consequences for the docs.

1. **What is the project's nature?** Is EventCommerce (a) a **reference / learning / portfolio project** whose primary purpose is to demonstrate event-driven architecture on a real ecommerce-shaped domain, or (b) a **commercial MVP** that must satisfy real customer expectations? This determines everything else — depth of NFRs in `ARCHITECTURE.md`, realism of `PRD.md` personas, ambition of `DESIGN.md`, and whether "no real payment provider" is acceptable.
2. **What is the MVP scope?** Should the MVP documented in `PRD.md` be (a) **just the core flow** (`Create order → Reserve inventory → Authorize payment → Confirm/cancel order → Send notification`, exercised end-to-end with the AMQP wiring bootstrapped), or (b) **storefront-shaped** (core flow + catalog browsing + cart + basic auth)? The user's framing leans (a), but this must be confirmed. Option (a) keeps MVP achievable; option (b) makes the foundation doc reference a 6–12 month build.
3. **What is the consistency model?** Should the architecture docs describe (a) **choreography with outbox + idempotency** (what the code today already does in spirit), (b) **choreography with outbox + a saga orchestrator** that adds explicit compensations, or (c) **orchestrated saga with a central coordinator**? Option (a) is what the code does and what the foundation should describe; (b) and (c) are target and should be called out as such.
4. **Where does auth live?** (a) **Out of scope for the MVP** (assume an external IdP and document the contract), (b) **A cross-cutting FastAPI middleware** that validates JWTs, or (c) **A dedicated `iam` bounded context** (login, signup, sessions, password reset, roles). The current code has none; the docs must say so and pick one for the target.
5. **Is the simulated payment acceptable as the documented contract?** `AuthorizePayment` uses a `random.choice([True, True, True, False])` approval policy. The foundation docs must be explicit that the MVP is **payment-agnostic** (the bounded context is real, the provider is a stub) so future readers do not believe the system processes real cards.

## suggested_document_set

Recommended root-level document set for this change, with explicit non-overlap. Anchors derived from `docs-writer`, `design-architecture`, and `cognitive-doc-design` skill contracts.

| Document | Path | One-line purpose | Authoritative for | Explicitly NOT authoritative for |
|---|---|---|---|---|
| `README.md` | `./README.md` | "What is EventCommerce, who is it for, and how do I get it running in 5 minutes." | Quick-path, project pitch, links to the other three docs, top-level repo layout, contribution pointer. | Product features, technical decisions, UI/UX details. |
| `PRD.md` | `./PRD.md` | "What the product is, who it serves, and what MVP success looks like." | Vision, problem statement, personas, user journeys (textual), MVP feature list, business rules, non-goals, success metrics, glossary. | Architecture, API contracts, data model, UI states, code structure. |
| `ARCHITECTURE.md` | `./ARCHITECTURE.md` | "How the system is built, why it is built that way, and how the pieces communicate." | System topology, bounded contexts, event-driven patterns (event store, outbox, AMQP, idempotency), cross-cutting concerns (config, errors, observability), NFRs, ADR index. | UX flows, product scope, individual file/class design. |
| `DESIGN.md` | `./DESIGN.md` | "How the product looks and feels, and how a user moves through it." | User flows (Now/Target), screen inventory, design tokens, component states, responsive behavior, accessibility. | Backend decisions, database choices, message format. |
| `docs/adr/` (optional) | `./docs/adr/` | "Record significant architectural decisions with context, options, and rationale." | ADR per significant decision (e.g., event store over per-module tables, choreography over orchestrated saga, dependency-injector as the DI library). Justified if `ARCHITECTURE.md` is going to reference decisions that the reader cannot easily reconstruct from code. | Anything already self-evident in code. |
| `docs/GLOSSARY.md` (optional) | `./docs/GLOSSARY.md` | "Shared vocabulary for domain terms and event names." | Domain language (`order`, `fulfillment`, `reservation`), event names with producer/consumer. Justified because event names are a contract and a glossary prevents doc drift. | Anything beyond shared vocabulary. |

Hard non-overlap rules:

- A user journey appears once in `PRD.md` (textual) and again in `DESIGN.md` (with UI states). The PRD version must not describe UI; the DESIGN version may quote PRD wording but not contradict it.
- The event-type vocabulary (`OrderCreated`, `InventoryReserved`, `InventoryRejected`, `OrderConfirmed`, `OrderCancelled`) appears in `ARCHITECTURE.md` (with payload schema) and in `docs/GLOSSARY.md` (with one-liner per event). `PRD.md` may use event names in user journeys but must link to the glossary for the canonical definition.
- `ARCHITECTURE.md` lists bounded contexts; `DESIGN.md` lists screens. The two lists intersect only in a mapping table at the end of `ARCHITECTURE.md` or the top of `DESIGN.md`; they must not be embedded in each other.
- `README.md` is the **only** doc that lists "how to run it" commands. `ARCHITECTURE.md` and `DESIGN.md` may link to it, not duplicate it.

## suggested_followup_changes

A small, sequenced set of SDD changes the orchestrator should propose **after** the foundation is merged. Each is sized to fit the 400-line review budget. The order is by dependency, not by priority.

1. **`integrate-development-environment`** — pyproject deps reconciliation, `pre-commit` (ruff, pyrefly, ruff format), GitHub Actions CI (lint + test), `AGENTS.md` for the repo, devcontainer (optional), Makefile/`justfile` for the common commands, definitive `.env.example`. Touches: `backend/pyproject.toml`, `backend/.env.example`, `.github/workflows/**`, `AGENTS.md`, `Makefile`, `.pre-commit-config.yaml`. **Does not touch app code.**
2. **`align-backend-readme-and-fix-stale-structure-doc`** — rewrite `backend/README.md` to match the post-refactor flat layout; remove the obsolete structural diagrams. Pure doc change, scoped to one file. Touches: `backend/README.md`.
3. **`fix-shared-events-broken-import-and-bootstrap-messaging`** — fix `app/shared/events/__init__.py` (delete the broken import line), bootstrap the outbox worker as a FastAPI lifespan task, add an `aio-pika` consumer that subscribes to the `order.events` topic exchange and dispatches `OrderCreated` → `ProcessInventoryReservation`, `InventoryReserved/Rejected` → `ProcessOrderInventoryResult`. Touches: `backend/app/shared/events/__init__.py`, `backend/app/app.py` (lifespan), new `backend/app/shared/messaging/consumer.py`, `backend/app/modules/orders/api/container.py` and `backend/app/modules/inventory/api/container.py` (wire the new use cases). Tests updated and re-enabled.
4. **`wire-inventory-payments-notifications-endpoints`** — finish the inventory/payments/notifications containers with real providers, expose minimal HTTP entry points needed by the event-driven flow (e.g., `POST /api/v1/inventory/{product_id}/reservations`, `GET /api/v1/payments/{order_id}`), update the global v1 router. Touches: the three `api/container.py` and `api/routes.py` and the global `api/v1/router.py`.
5. **`mvp-core-flow-vertical-slice-e2e`** — replace the AMQP-bypassing `test_core_flow.py` with a true end-to-end test that boots the consumer, sends a real AMQP message, and asserts on the resulting order status, inventory, outbox, and event store. Touches: `backend/app/tests/test_core_flow.py` and any required harness (testcontainers, RabbitMQ test broker). Pure test change.
6. **`add-catalog-bounded-context`** — add `catalog` module (entities, repository, HTTP, container, migrations). Touches: new `backend/app/modules/catalog/**`, `backend/app/api/v1/router.py`, `backend/alembic/versions/...`.
7. **`add-cart-bounded-context`** — add `cart` module. Touches: same as catalog.
8. **`add-iam-auth`** — bounded context for auth (or FastAPI middleware, depending on the answer to product question 4). Touches: new `backend/app/modules/iam/**` or `backend/app/shared/auth/**` plus the OpenAPI security scheme.
9. **`add-saga-and-dlq`** — replace ad-hoc outbox handling with an explicit saga/coordinator and a DLQ. Touches: `backend/app/shared/messaging/**` plus consumer dispatch logic.
10. **`add-observability-and-runbooks`** — `structlog`, OpenTelemetry traces, `/health/ready` for Postgres/RabbitMQ, Prometheus metrics, runbooks. Touches: `backend/app/app.py`, `backend/app/shared/**`, `docs/runbooks/**`.
11. **`add-frontend-mvp`** — only after the foundation and at least changes 3–5 are merged. Out of scope for the docs change.

## Ready for Proposal

**Yes, with a precondition.**

Precondition: the orchestrator must surface `product_questions_for_proposal` (above) to the user before drafting the proposal. The answer to question 1 (project nature) and question 2 (MVP scope) materially change the content of `PRD.md`; question 3 (consistency model) materially changes the content of `ARCHITECTURE.md`; question 4 (auth) and question 5 (simulated payment) change the non-goals and the bounded-context list. Drafting the proposal without these answers risks re-doing half of it.

When the proposal is drafted:

- It must specify the per-doc ordering (`README → PRD → ARCH → DESIGN`), the per-doc work-unit size (each < 400 review lines), and the cross-doc contracts (event vocabulary, bounded-context names, order state machine) that the docs MUST honor.
- It must include a "current vs target" table per major area in each doc, to keep the foundation honest about what is on disk.
- It must declare which optional docs (`docs/adr/`, `docs/GLOSSARY.md`) are in-scope and justify each inclusion.
- It must explicitly note that no code, no setup, no frontend, no GitHub workflows, and no backend file other than root docs is touched.
