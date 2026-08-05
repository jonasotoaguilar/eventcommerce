# Design: Checkout End-to-End

## Technical Approach

Add A1+B3+C1+P2 synchronous `checkout` and `POST /api/v1/checkout`. A request-local SQLAlchemy session atomically coordinates commerce, outbox, and idempotency; post-commit notification needs no RabbitMQ/scheduler and leaves the three-state order unchanged.

## Architecture Decisions

| Concern | Alternatives / tradeoff | Decision and rationale |
|---|---|---|
| Price trust | Treat caller input as price/currency authority; add catalog | `amount`/`currency` are validated **simulated-payment input**, never authoritative pricing or currency proof. Reconciliation remains deferred to catalog. |
| Atomicity | Commit each use case; saga | One core DB transaction. Existing repositories flush without committing, so rollback can undo every commerce write and is the smallest safe boundary. |
| Idempotency | Derive response; in-memory cache | Extend `processed_events`; durable exact response reuse and cross-process concurrency require persisted claim metadata. |
| Notification | Include with commerce; require AMQP | Persist the terminal commerce outbox atomically. For each terminal state, after commit attempt exactly one notification intent via `SendOrderNotification`; log failure and never roll back commerce. |
| Payment math | Float; configurable probability | Use `Decimal` and fixed threshold `192` (75%). A code constant preserves reproducibility across deployments. |

## Components and Sequence

`checkout/api/routes.py` maps HTTP; request-local `CheckoutContainer` supplies one session. `Checkout` alone owns terminal order transition. `ProcessOrderInventoryResult` is **not invoked** synchronously; it remains AMQP-only. `AuthorizePayment` owns Payment persistence; the orchestrator **MUST NOT create Payment records**. Module containers gain providers; checkout uses no global session override.

```text
route -> advisory lock/claim -> create order -> lock+reserve inventory
  insufficient -> cancel ---------------------------> terminal outbox
  reserved -> authorize+persist payment
    approved -> confirm ----------------------------> terminal outbox
    declined -> persist PaymentFailed -> release -> cancel -> terminal outbox
-> cache status/body -> COMMIT -> exactly-one notification-intent attempt -> 201
```

Inventory rows are locked `FOR UPDATE` in sorted `product_id` order and all lines are checked before mutation. On decline, failure record, release, cancellation, outbox, and idempotency completion remain uncommitted until one final commit. Any later persistence error rolls back the original reservation; it cannot remain reserved.

## API and Data Contracts

`CheckoutRequest`: `customer_id`/`product_id` 1–128 characters; 1–100 unique items; quantity 1–10,000; `amount: Decimal` 0–999,999,999.99 with at most two decimals; currency normalized then validated syntactically as exactly three uppercase ASCII letters (`^[A-Z]{3}$`). This does not prove an ISO 4217 currency exists; authoritative currency/pricing reconciliation is deferred to catalog. `Idempotency-Key` is optional, 1–128 visible ASCII characters. `CheckoutResponse` stores `order_id`, `status`, nullable `cancel_reason`, and nullable `payment_status`; every created terminal order returns `201`. Validation=`422`, key/payload mismatch=`409`, unexpected database failure rolls back and returns `500`.

Canonical payment bytes are UTF-8 `lowercase-hyphenated-uuid|amount-to-2-decimals|UPPERCASE-CURRENCY`; approve iff SHA-256 byte 0 `< 192`. Vectors: `00000000-0000-0000-0000-000000000001|19.99|USD` → `0x12` approved; `...|0.00|USD` → `0xc9` declined; `19.9` canonicalizes to `19.90`.

The payload hash is SHA-256 over compact, sorted-key normalized-request JSON (item order retained). `processed_events.event_id` changes UUID→Text; add nullable `payload_hash CHAR(64)`, `response_status`, `response_body JSON`, `updated_at`, plus non-null `state` (`processed|in_progress|completed`). Existing rows backfill `processed`. Checkout acquires `pg_advisory_xact_lock(hashtextextended('Checkout:' || key,0))`, then atomically inserts/reads `(key,'Checkout')`: mismatch conflicts; completed replays; concurrent identical requests wait then replay. Rollback removes uncommitted claims. Bodies are capped at 16 KiB.

## Files and Persistence

| Action | Paths |
|---|---|
| Create | `app/modules/checkout/{application/checkout.py,api/{container.py,routes.py,schemas.py}}`; `alembic/versions/*_extend_checkout_idempotency.py`; checkout tests |
| Modify | `app/app.py`; order/inventory/payment/notification containers and use cases; inventory repository port/SQL locking; payment entity/model/repository/policy; `shared/messaging/{idempotency.py,models.py,envelope.py}`; ADR 0005 status only |
| Delete | `app/modules/orders/infrastructure/repositories/sqlalchemy_repository.py` dead stub |

Migration also changes `payments.amount` Float→`NUMERIC(11,2)`. Constraints preserve the composite key and require completed checkout rows to have hash/status/body. Downgrade removes checkout metadata, casts UUID-compatible event IDs back, and restores Float; deploy migration before route. Rollback application first, then downgrade only after confirming no non-UUID keys exist.

## Observability and Testing

Log structured `checkout_started/completed/replayed/conflict/rolled_back/notification_failed` with order ID, outcome, duration, and a key-hash prefix—never raw keys or payloads.

Unit tests cover canonicalization/vectors, limits, payload hashing, and ownership. PostgreSQL tests cover migration constraints, advisory-lock races, exact replay, row locking, rollback after release/cancel failure, and post-commit notification failure. HTTP E2E covers happy, rejection paths, no-key duplication, `422/409/201`, outbox, and notification intent.

## Threat Matrix

| Boundary | Applicability | Design response / RED tests |
|---|---|---|
| Documentation-like paths | N/A — no file classification/execution | None |
| Git repository selection | N/A — no VCS commands | None |
| Commit state | N/A — no VCS automation | None |
| Push state | N/A — no push automation | None |
| PR commands | N/A — no PR automation | None |

HTTP routing validation and status mapping are covered by E2E tests.

## Work Slices and Open Questions

1. Migration + idempotency/concurrency tests. 2. Decimal payment policy/failure event + ADR status. 3. Inventory locking + checkout/DI/API/E2E. `sdd-tasks` must forecast against the 800-line review budget before resolving auto-chain boundaries.

Open questions: None.
