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
| Event envelope | The canonical wire format that carries event metadata and payload across contexts. | MVP Target |
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

Current events live in per-module `domain/events/` files. The shared envelope and the target event vocabulary are **MVP Target** and will live in `backend/app/shared/messaging/envelope.py`.

### Current events (Now)

| Event | Meaning | Producer | Consumer | Code path |
|---|---|---|---|---|
| `OrderCreated` | A shopper submitted a checkout and an order aggregate was created. | `orders` | `inventory` (Target), `notifications` (Target) | `backend/app/modules/orders/domain/events/order_events.py` |
| `InventoryReserved` | Requested stock was reserved successfully. | `inventory` | `orders` (Target), `payments` (Target) | `backend/app/modules/inventory/domain/events/inventory_events.py` |
| `PaymentAuthorized` | A payment was authorized for the order. | `payments` | `orders` (Target), `notifications` (Target) | `backend/app/modules/payments/domain/events/payment_events.py` |
| `OrderNotificationSent` | A notification was dispatched for an order. | `notifications` | — | `backend/app/modules/notifications/domain/events/notification_events.py` |

### Target events (MVP Target)

The choreography target adds the shared envelope and these additional events:

| Event | Meaning | Producer | Consumer |
|---|---|---|---|
| `InventoryRejected` | Requested stock could not be reserved. | `inventory` | `orders` |
| `OrderConfirmed` | The order reached a terminal successful state. | `orders` | `notifications` |
| `OrderCancelled` | The order reached a terminal cancelled state. | `orders` | `inventory`, `notifications` |

## State vocabulary

### Order status

Order statuses are `pending`, `inventory_reserved`, `payment_authorized`, `confirmed`, and `cancelled`. The allowed transitions are defined by `can_transition` in `backend/app/modules/orders/domain/services/order_domain_service.py`.

| From | To | Allowed | Notes |
|---|---|---|---|
| `pending` | `inventory_reserved` | Yes | Triggered after stock reservation succeeds. |
| `pending` | `cancelled` | Yes | Triggered when stock is rejected or payment is rejected. |
| `inventory_reserved` | `payment_authorized` | Yes | Triggered after payment authorization succeeds. |
| `inventory_reserved` | `cancelled` | Yes | Triggered when payment is rejected. |
| `payment_authorized` | `confirmed` | Yes | Triggered after final acceptance. |
| `payment_authorized` | `cancelled` | Yes | Triggered when final acceptance fails. |
| `confirmed` | `pending` / `inventory_reserved` / `payment_authorized` / `cancelled` | No | Terminal state. |
| `cancelled` | `pending` / `inventory_reserved` / `payment_authorized` / `confirmed` | No | Terminal state. |

## Maintenance

1. A code-contract change (event name, order status, bounded-context name, stack component) must update this glossary and any affected root doc in the same change.
2. The **Current events** table reflects the per-module `domain/events/` files. The **Target events** table will match the `event_type` `Literal[...]` in `backend/app/shared/messaging/envelope.py` once the envelope is implemented.
3. The **Order status** transitions must match `backend/app/modules/orders/domain/services/order_domain_service.py` exactly.
4. Do not describe unwired AMQP consumers or absent shared infrastructure as live. Use `MVP Target` for capabilities that have no code in the published tree.
