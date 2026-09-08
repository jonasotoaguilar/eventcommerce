# Delta for project-foundation-docs

## MODIFIED Requirements

### Requirement: Now / MVP Target / Future Honesty Rule

Every capability claim MUST be tagged Now, MVP Target, or Future. `ARCHITECTURE.md` MUST include a Current Implementation Status matrix (Decision, Status `implemented`/`partial`/`target`, Code evidence, Doc location). `DESIGN.md` is target; only its Now column binds. No present-tense for non-implemented capabilities. When the messaging runtime ships, its matrix rows (publisher, outbox worker, consumer runtime) MUST be marked `implemented` with code-evidence pointers; undeployed messaging capabilities stay tagged Target/Future.
(Previously: assumed the AMQP consumer and outbox worker were not yet bootstrapped)

#### Scenario: Status matrix and language are honest about the delivered runtime

- GIVEN the messaging runtime is delivered (publisher, outbox scheduler, consumer runtime wired)
- WHEN a reviewer reads the matrix and greps `PRD.md` + `ARCHITECTURE.md` for messaging claims
- THEN delivered rows carry Status `implemented` with code-evidence pointers AND no capability beyond delivered behavior uses present-tense business language

### Requirement: Code-Contract Lock-In — Source Hierarchy

Docs MUST honor the source hierarchy. Published Git Now is the binding reference for current-state claims. MVP Target contracts are sourced from the dirty refactor branch.

#### Now (Published Git)

| Contract | Value | Evidence |
|---|---|---|
| Current Events | `OrderCreated` (orders), `InventoryReserved` (inventory), `InventoryRejected` (orders/inventory), `OrderConfirmed` (orders/checkout), `OrderCancelled` (orders/checkout), `PaymentAuthorized` (payments), `OrderNotificationSent` (notifications) | `backend/app/modules/orders/domain/events.py`, `backend/app/modules/{checkout,inventory,orders}/application/`, and the existing event-store/outbox tests |
| State Machine | `pending→{confirmed,cancelled}` (Phase 1; self-transitions allowed for idempotency) | `backend/app/modules/orders/domain/services.py` `can_transition()` |
| Shared messaging foundation | Event store, transactional outbox, idempotency primitives, and the PR1 outbox durability work; AMQP publisher forwarding and consumer runtime are not live before their later runtime slices | `backend/app/shared/events/`, `backend/app/shared/messaging/`, `backend/app/modules/checkout/application/` |
| Current Contexts | `orders`, `inventory`, `payments`, `notifications` | `backend/app/modules/` |
| Stack | Py3.13+, FastAPI, SQLAlchemy 2 async, Pydantic Settings 2.x, Alembic, `uv` | Published code |

#### MVP Target (source: dirty refactor branch)

| Contract | Value |
|---|---|
| Target Delivery | AMQP forwarding and consumer delivery of the current event vocabulary (shared envelope) |
| Target Contexts | `iam`, `catalog`, `cart` |
| Target Stack | `dependency-injector`, `aio-pika`, shared event store, outbox, idempotency store |

A current-capability claim MUST be backed by an existing `backend/app/` file in the published tree; otherwise the claim is tagged MVP Target.

#### Scenario: Current event vocabulary matches published per-module classes

- GIVEN the docs list current event types; WHEN a reviewer checks each against the per-module `domain/events/*.py` dataclass names in the published tree; THEN the sets match exactly

#### Scenario: No invented current capability

- GIVEN a doc claims a current capability; WHEN a reviewer locates the implementing code; THEN the file exists in `backend/app/` in the published tree and is referenced in the status matrix, OR the claim is tagged Target

## ADDED Requirements

### Requirement: Messaging Delivery Evidence in Docs

The change that ships the messaging runtime MUST update, in the same change: `ARCHITECTURE.md` status matrix rows (publisher, outbox worker, consumer runtime), `docs/GLOSSARY.md` consumer-wiring and queue-binding entries, `docs/adr/0002-use-choreography.md` delivery status, and `README.md` status snapshot. No doc MUST claim AMQP is live before the runtime ships.

#### Scenario: Docs updated in the same change

- GIVEN the messaging runtime change is merged
- WHEN a reviewer checks the four doc surfaces
- THEN matrix rows, glossary wiring, ADR status, and README snapshot match delivered behavior

#### Scenario: No premature AMQP claims

- GIVEN the runtime is not yet delivered
- WHEN docs are reviewed
- THEN no doc claims AMQP consumers or the outbox worker are live
