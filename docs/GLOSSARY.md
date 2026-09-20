# Glossary

Canonical domain and event vocabulary for `eventcommerce`. Use this document to keep product and implementation language aligned. Product intent lives in [PRD.md](../PRD.md); target UX lives in [DESIGN.md](../DESIGN.md).

## Usage

- Reference these terms when writing code, docs, tests, or ADRs.
- Keep product narrative in the PRD; keep event ownership and state rules here.
- Update this file when a code contract changes (event name, status value, bounded context, stack component).

## Domain terms

| Term | Definition | Horizon |
|---|---|---|
| Bounded context | A module that owns its own domain model, data, and invariants (e.g., `orders`, `inventory`, `checkout`). | Now / Target |
| Event envelope | The canonical wire format that carries event metadata and payload across contexts. Defined at `backend/app/shared/messaging/envelope.py` and carried across contexts by the wired runtime (publisher + AMQP consumer); live delivery requires RabbitMQ. | Now |
| Choreography | Contexts react to published events rather than following a central orchestrator. Wired at runtime (`backend/app/messaging_runtime.py` + `backend/app/shared/messaging/consumer.py`); see Consumer wiring. | Now |
| Transactional outbox | Events are persisted atomically with business state, then forwarded to a broker. Emission (`outbox_events`) and forwarding (outbox scheduler + RabbitMQ publisher in `backend/app/messaging_runtime.py`) are wired; live delivery requires RabbitMQ. | Now |
| Idempotency | Processing the same event twice must not duplicate side effects. Implemented for the checkout path (`processed_events`) and enforced per-message by the wired AMQP handlers in the same consumer transaction. | Now |
| Deterministic simulated payment | A payment provider that returns the same authorization result for the same inputs. Implemented in `backend/app/modules/payments/domain/policy.py` (ADR 0005). | Now |
| Principal | The authenticated caller carried as `CurrentUser` after bearer verification (`backend/app/modules/iam/api/dependencies.py`, `backend/app/modules/iam/application/tokens.py`). | Now |
| Shopper | The default role assigned at registration (`backend/app/modules/iam/application/register_user.py`); owns only its own commerce resources. | Now |
| Operator | The privileged role allowed alongside the owner on commerce reads (`backend/app/modules/orders/api/routes.py`). | Now |
| Subject | The JWT `sub`/`user_id` identifying the caller; commerce derives ownership from it instead of trusting client-sent IDs. | Now |
| Bearer | The HTTP `Authorization: Bearer <access_token>` credential verified by `get_current_user` (`401` when missing, invalid, or expired). | Now |

### Bounded contexts

**Current contexts** (`backend/app/modules/`):

- `orders` — order lifecycle and state machine.
- `checkout` — synchronous commerce orchestrator (`POST /api/v1/checkout`; inline items or `cart_id` with catalog-derived pricing).
- `inventory` — stock reservation and release with row-level locking; operator stock adjustment.
- `payments` — authorization and failure handling behind a deterministic policy.
- `notifications` — best-effort notification intent.
- `iam` — JWT authentication and role authorization.
- `catalog` — product browsing (public active-only) and operator product management; creation seeds the inventory row.
- `cart` — one persisted cart per authenticated shopper with live subtotal from catalog prices.

**Target contexts** (MVP): no new bounded contexts remain; remaining work extends `orders` toward the five-state lifecycle.

## Events

The shared envelope at `backend/app/shared/messaging/envelope.py` defines the canonical `event_type` literal: `OrderCreated`, `InventoryReserved`, `InventoryRejected`, `OrderConfirmed`, and `OrderCancelled`. The shared event store (`backend/app/shared/events/`) persists timeline events; the transactional outbox (`backend/app/shared/messaging/outbox_repository.py`) persists events for later forwarding. Only the `orders` context defines domain event dataclasses today (`backend/app/modules/orders/domain/events.py`); inventory, payments, and notifications have no per-module events module.

### Current events (Now)

| Event | Meaning | Producer | Consumer | Code path |
|---|---|---|---|---|
| `OrderCreated` | A shopper submitted a checkout and an order aggregate was created. | `orders` (via `CreateOrder`) | `ProcessInventoryReservation` via `inventory.order_created` | `backend/app/modules/orders/domain/events.py`; persisted to `domain_events` and `outbox_events` |
| `OrderConfirmed` | The order reached the `confirmed` terminal state. | `checkout` | `ProcessOrderNotification` via `notifications.order_terminal` (plus best-effort sync notify) | Outbox write in `backend/app/modules/checkout/application/checkout.py` |
| `OrderCancelled` | The order reached the `cancelled` terminal state. | `checkout` | `ProcessOrderNotification` via `notifications.order_terminal`; inventory release (on payment failure) | Outbox write in `backend/app/modules/checkout/application/checkout.py` |
| `InventoryReserved` | Requested stock was reserved successfully. | `checkout` (via inventory use cases) | `ProcessOrderInventoryResult` via `orders.inventory_result` | Envelope literal; `orders/domain/events.py` dataclass |
| `InventoryRejected` | Requested stock could not be reserved. | `checkout` (via inventory use cases) | `ProcessOrderInventoryResult` via `orders.inventory_result` | Envelope literal; `orders/domain/events.py` dataclass |

### Consumer wiring (Now)

The choreography runtime wires these events to consumers through the outbox, RabbitMQ publisher, and AMQP consumer (`backend/app/messaging_runtime.py`, durable `order.events` TOPIC exchange): `inventory.order_created` carries `OrderCreated` → `ProcessInventoryReservation`; `orders.inventory_result` carries `InventoryReserved`/`InventoryRejected` → `ProcessOrderInventoryResult`; `notifications.order_terminal` carries `OrderConfirmed`/`OrderCancelled` → `ProcessOrderNotification`. The synchronous checkout path is retained alongside the wired consumers. Live broker delivery requires RabbitMQ (gated CI integration); the default suite proves the chain broker-free (`backend/app/tests/runtime/test_chain_e2e.py`).

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
4. Do not describe undeployed messaging capabilities as live. Broker delivery requires RabbitMQ; production deployment and operations are out of scope (no such claim is made here).
