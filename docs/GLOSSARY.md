# Glossary

Canonical domain and event vocabulary for `eventcommerce`. Use this document to keep product and implementation language aligned. Product intent lives in [PRD.md](../PRD.md); system structure lives in [ARCHITECTURE.md](../ARCHITECTURE.md); target UX lives in [DESIGN.md](../DESIGN.md).

## Usage

- Reference these terms when writing code, docs, tests, or ADRs.
- Keep product narrative in the PRD; keep event ownership and state rules here.
- Update this file when a code contract changes (event name, status value, bounded context, stack component).

## Domain terms

| Term | Definition | Horizon |
|---|---|---|
| Bounded context | A module that owns its own domain model, data, and invariants (e.g., `orders`, `inventory`). | Now / Target |
| Event envelope | The canonical wire format that carries event metadata and payload across contexts. | Now |
| Choreography | Contexts react to published events rather than following a central orchestrator. | MVP Target |
| Transactional outbox | Events are persisted atomically with business state, then forwarded to a broker. | MVP Target |
| Idempotency | Processing the same event twice must not duplicate side effects. | MVP Target |
| Deterministic simulated payment | A payment provider that returns the same authorization result for the same inputs. | MVP Target |

### Bounded contexts

**Current contexts** (`backend/app/modules/`):

- `orders` — order lifecycle and state machine.
- `inventory` — stock reservation and release.
- `payments` — authorization and failure handling.
- `notifications` — reactions to order events.

**Target contexts** (MVP):

- `iam` — owned JWT authentication and role authorization.
- `catalog` — product browsing and catalog management.
- `cart` — purchase collection before checkout.

## Events

The event vocabulary is locked to the `event_type` `Literal[...]` in [`backend/app/shared/messaging/envelope.py`](../backend/app/shared/messaging/envelope.py). Do not add, remove, or reorder rows without updating the code literal in the same change.

| Event | Meaning | Producer | Consumer | Horizon | Status |
|---|---|---|---|---|---|
| `OrderCreated` | A shopper submitted a checkout and an order aggregate was created. | `orders` | `inventory` (reserve stock); `notifications` (target) | Now | Partial — event is emitted; AMQP consumer is not yet live. |
| `InventoryReserved` | Requested stock was reserved successfully. | `inventory` | `orders` (confirm); `payments` (authorize) | Now | Partial — domain event exists; wired consumer is not yet live. |
| `InventoryRejected` | Requested stock could not be reserved. | `inventory` | `orders` (cancel) | Now | Partial — domain event exists; wired consumer is not yet live. |
| `OrderConfirmed` | The order reached a terminal successful state. | `orders` | `notifications` (target) | Now | Partial — domain event exists; wired consumer is not yet live. |
| `OrderCancelled` | The order reached a terminal cancelled state. | `orders` | `inventory` (release stock); `notifications` (target) | Now | Partial — domain event exists; wired consumer is not yet live. |

## State vocabulary

### Order status

Order statuses are `pending`, `confirmed`, and `cancelled`. The allowed transitions are defined by `can_transition` in [`backend/app/modules/orders/domain/services.py`](../backend/app/modules/orders/domain/services.py).

| From | To | Allowed | Notes |
|---|---|---|---|
| `pending` | `pending` | Yes | Idempotent self-transition. |
| `pending` | `confirmed` | Yes | Triggered after `InventoryReserved`. |
| `pending` | `cancelled` | Yes | Triggered after `InventoryRejected` or payment failure. |
| `confirmed` | `confirmed` | Yes | Idempotent self-transition. |
| `confirmed` | `pending` / `cancelled` | No | Terminal state. |
| `cancelled` | `cancelled` | Yes | Idempotent self-transition. |
| `cancelled` | `pending` / `confirmed` | No | Terminal state. |

## Maintenance

1. A code-contract change (event name, order status, bounded-context name, stack component) must update this glossary and any affected root doc in the same change.
2. The **Events** table order must match `backend/app/shared/messaging/envelope.py` exactly.
3. The **Order status** transitions must match `backend/app/modules/orders/domain/services.py` exactly.
4. Do not describe unwired AMQP consumers as live. Use `Partial` for events that exist in code but lack a running consumer.
