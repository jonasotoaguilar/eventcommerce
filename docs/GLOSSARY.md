# Glossary

Canonical domain and event vocabulary for `eventcommerce`. Use this document to keep product and implementation language aligned. Product intent lives in [PRD.md](../PRD.md); system structure lives in [ARCHITECTURE.md](../ARCHITECTURE.md); target UX lives in [DESIGN.md](../DESIGN.md).

## Usage

- Reference these terms when writing code, docs, tests, or ADRs.
- Keep product narrative in the PRD; keep event ownership and state rules here.
- Update this file when a code contract changes (event name, status value, bounded context, stack component).

## Domain terms

| Term | Definition | Horizon |
|---|---|---|
| Bounded context | A module that owns its own domain model, data, and invariants (e.g., `orders`, `inventory`, `checkout`). | Now / Target |
| Event envelope | The canonical wire format that carries event metadata and payload across contexts. The model exists at `backend/app/shared/messaging/envelope.py`; using it across contexts via a broker is MVP Target. | Now (structure) / Target (use) |
| Choreography | Contexts react to published events rather than following a central orchestrator. | MVP Target |
| Transactional outbox | Events are persisted atomically with business state, then forwarded to a broker. Emission is implemented (`outbox_events`); forwarding to a broker is not wired. | Now (emission) / Target (forwarding) |
| Idempotency | Processing the same event twice must not duplicate side effects. Implemented for the checkout path (`processed_events`); wired AMQP consumers are MVP Target. | Now (checkout path) |
| Deterministic simulated payment | A payment provider that returns the same authorization result for the same inputs. Implemented in `backend/app/modules/payments/domain/policy.py` (ADR 0005). | Now |

### Bounded contexts

**Current contexts** (`backend/app/modules/`):

- `orders` — order lifecycle and state machine.
- `checkout` — synchronous commerce orchestrator (`POST /api/v1/checkout`).
- `inventory` — stock reservation and release with row-level locking.
- `payments` — authorization and failure handling behind a deterministic policy.
- `notifications` — best-effort notification intent.

**Target contexts** (MVP):

- `iam` — owned JWT authentication and role authorization.
- `catalog` — product browsing and catalog management.
- `cart` — purchase collection before checkout.

## Events

The shared envelope at `backend/app/shared/messaging/envelope.py` defines the canonical `event_type` literal: `OrderCreated`, `InventoryReserved`, `InventoryRejected`, `OrderConfirmed`, and `OrderCancelled`. The shared event store (`backend/app/shared/events/`) persists timeline events; the transactional outbox (`backend/app/shared/messaging/outbox_repository.py`) persists events for later forwarding. Only the `orders` context defines domain event dataclasses today (`backend/app/modules/orders/domain/events.py`); inventory, payments, and notifications have no per-module events module.

### Current events (Now)

| Event | Meaning | Producer | Consumer | Code path |
|---|---|---|---|---|
| `OrderCreated` | A shopper submitted a checkout and an order aggregate was created. | `orders` (via `CreateOrder`) | AMQP consumers (Target) | `backend/app/modules/orders/domain/events.py`; persisted to `domain_events` and `outbox_events` |
| `OrderConfirmed` | The order reached the `confirmed` terminal state. | `checkout` | Notifications (best-effort sync); AMQP consumers (Target) | Outbox write in `backend/app/modules/checkout/application/checkout.py` |
| `OrderCancelled` | The order reached the `cancelled` terminal state. | `checkout` | Inventory release (on payment failure); AMQP consumers (Target) | Outbox write in `backend/app/modules/checkout/application/checkout.py` |
| `InventoryReserved` | Requested stock was reserved successfully. | `checkout` (via inventory use cases) | AMQP consumers (Target) | Envelope literal; `orders/domain/events.py` dataclass |
| `InventoryRejected` | Requested stock could not be reserved. | `checkout` (via inventory use cases) | AMQP consumers (Target) | Envelope literal; `orders/domain/events.py` dataclass |

### Consumer wiring (MVP Target)

The choreography target wires these events to consumers through the outbox, RabbitMQ publisher, and AMQP consumer. When that wiring is live, `OrderCreated` triggers inventory reservation, `InventoryReserved` / `InventoryRejected` drive order confirmation or cancellation, and terminal events trigger notifications. Until then, none of these events are forwarded to a broker and no consumer reacts to them.

## State vocabulary

### Order status

Order statuses are `pending`, `confirmed`, and `cancelled` in the current machine, with `inventory_reserved` and `payment_authorized` reserved for the MVP Target five-state lifecycle. The allowed transitions are defined by `can_transition` in `backend/app/modules/orders/domain/services.py`.

| From | To | Allowed | Notes |
|---|---|---|---|
| `pending` | `confirmed` | Yes | Reached by the synchronous checkout when payment is authorized. |
| `pending` | `cancelled` | Yes | Reached when stock is rejected or payment is rejected. |
| `confirmed` | `confirmed` | Yes | Idempotent self-transition; terminal state. |
| `cancelled` | `cancelled` | Yes | Idempotent self-transition; terminal state. |
| `confirmed` | any other | No | Terminal state. |
| `cancelled` | any other | No | Terminal state. |

MVP Target adds the intermediate states: `pending` → `inventory_reserved` → `payment_authorized` → `confirmed`/`cancelled`, with cancellation allowed from any non-terminal state.

## Maintenance

1. A code-contract change (event name, order status, bounded-context name, stack component) must update this glossary and any affected root doc in the same change.
2. The **Current events** table reflects the shared envelope `event_type` literal in `backend/app/shared/messaging/envelope.py`, the domain event dataclasses in `backend/app/modules/orders/domain/events.py`, and the outbox emissions from the checkout path. Keep it in sync with those files.
3. The **Order status** transitions must match `backend/app/modules/orders/domain/services.py` exactly.
4. Do not describe unwired AMQP consumers or absent broker wiring as live. Use `MVP Target` for capabilities that have no runtime wiring; use `Now (emission)` / `Target (forwarding)` for partial capabilities.
