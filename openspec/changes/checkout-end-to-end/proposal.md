# Proposal: Checkout End-to-End (Synchronous Orchestrator)

## Intent

Connect the four existing backend modules (orders, inventory, payments, notifications) in one real HTTP checkout flow. Today the "end-to-end" test stops at the inventory boundary, `AuthorizePayment` is a non-deterministic `random.choice` stub (ADR 0005 unimplemented), and no checkout entry point exists. Value: first happy path spanning all four modules; reproducible demos; a retry-safe purchase — without forcing AMQP readiness.

## Capabilities

> Contract for `sdd-spec`. Existing specs: `project-foundation-docs` only (untouched). Verified via `openspec/specs/`.

### New Capabilities
- `checkout`: synchronous orchestrator, `POST /api/v1/checkout`, the `Idempotency-Key` product contract, the single-terminal-transition ownership invariant, payment-declined compensation, and the deterministic payment authorization policy (P2). No independent `payments` spec exists today, so the policy is specified within this capability.

### Modified Capabilities
- None (ADR 0005 status edit and stale-docs are documentation-only, not spec-level).

## Key Contracts

| Concern | Decision |
|---|---|
| Ownership | Orchestrator owns **exactly one** terminal order transition per request. Inner use cases (reserve/release/payment) MUST NOT confirm or cancel. `ProcessOrderInventoryResult` is **not** invoked synchronously — it stays the AMQP-path owner. |
| Compensation | Payment declined after reservation → `ReleaseInventory` then `CancelOrder(reason="payment_declined")`. Insufficient stock → `CancelOrder(reason="insufficient_stock")`. `cancel_reason` set once, only by the orchestrator. |
| Idempotency | `Idempotency-Key` header dedups via `ProcessedEventStore` keyed `(key, "Checkout")`. Replay **same key + same payload** → return cached terminal response, no re-execution (no double-charge, no double-reserve). Key reused with **differing payload** → `409 Conflict`, no execution. Missing key → non-idempotent new order. |
| Replay storage | `ProcessedEventStore` dedups only today. Design selects a **durable** response cache via the Alembic migration (`event_id` Text, `payload_hash`, `response_status`/`response_body`, `state`) plus `pg_advisory_xact_lock` for cross-process safety. |
| Payment | `approved = sha256(f"{order_id}|{amount}|{currency}").digest()[0] < threshold`. Same input ⇒ same result (ADR 0005 P2). |
| Order state | Keep the 3-state model (`pending/confirmed/cancelled`); the orchestrator's `ConfirmOrder` moves `pending → confirmed`. The 5-state machine is deferred. |

## Scope

### In Scope
- New `backend/app/modules/checkout/`: `Checkout` use case, `POST /api/v1/checkout`, `CheckoutRequest`/`CheckoutResponse` schemas.
- Wire `ConfirmOrder`, `CancelOrder`, `ProcessOrderInventoryResult` into `OrdersContainer`; add `PaymentsContainer` providers.
- Replace `random.choice` with P2; implement `ProcessPaymentFailure` (persist `PaymentFailed`; do **not** cancel — orchestrator owns cancellation).
- `Idempotency-Key` wiring + durable response cache in `ProcessedEventStore`.
- `test_checkout_end_to_end.py`: happy path, payment rejected, insufficient stock, idempotent replay, key/payload mismatch `409`, payment-policy unit test.
- Update `docs/adr/0005-…md` → "Accepted (current implementation)".
- Remove dead stub `orders/infrastructure/repositories/sqlalchemy_repository.py` (one file, zero production imports — may split to a dedicated chore PR).

### Out of Scope
Catalog, cart, IAM (customer is `str`; items inline `{product_id, quantity}`); AMQP consumer + outbox scheduler + lifespan; 5-state order machine; confirm/cancel HTTP routes; stale foundation-docs realignment (README/PRD/ARCHITECTURE/ADRs/GLOSSARY) — a separate `realign-stale-documentation` follow-up, **not** scope creep.

## Approach

Synchronous orchestrator (exploration's A1 + B3 + C1 + P2). Inner steps stay individually callable so the AMQP follow-up is a refactor, not a rewrite; outbox rows are still written. Likely slices (final split in `sdd-tasks`): **(1)** Alembic migration + idempotency/concurrency; **(2)** Decimal payment policy + `PaymentFailed` event + ADR status; **(3)** inventory locking + checkout/DI/API/E2E; dead-stub deletion may be an isolated chore.

## Affected Areas

| Area | Impact |
|---|---|
| `backend/app/modules/checkout/` (new) | New — orchestrator, route, schemas |
| `modules/orders/api/container.py`, `app.py` | Modified — wiring + router |
| `modules/payments/application/{authorize_payment,process_payment_failure}.py` | Modified — P2 + failure impl |
| `modules/payments/api/container.py` | Modified — providers |
| `modules/payments/...` (entity/model/repository) | Modified — `amount` Float→`NUMERIC(11,2)` |
| `shared/messaging/idempotency.py` | Modified — durable response cache + claim state |
| `shared/messaging/models.py` | Modified — `ProcessedEventModel` (`event_id` Text, `payload_hash`, `response_status`/`response_body`, `state`) |
| `alembic/versions/*_extend_checkout_idempotency.py` (new) | New — schema migration |
| `docs/adr/0005-…md` | Modified — status |
| `orders/infrastructure/repositories/sqlalchemy_repository.py` | Removed — dead stub |
| `tests/test_checkout_end_to_end.py` | New |

## Risks

| Risk | L | Mitigation |
|---|---|---|
| ~600–900 lines near the 800 budget | Med | Forecast in `sdd-tasks`; split into the three slices above |
| `ProcessedEventStore` lacked a response cache | Low | Resolved by design — durable cache via the Alembic migration (not in-memory) |
| Double-cancel if an inner use case cancels | Med | Ownership invariant; integration test asserts exactly one transition |
| Reviewers think capabilities are "future" | High | Stale-docs follow-up is flagged separately, not folded in |

## Rollback Plan

**App first, then DB.** Revert the application PR(s) so `/checkout` and the P2 policy stop running; ADR 0005 status reverts to "Accepted (MVP Target)". This change ships one Alembic migration (`..._extend_checkout_idempotency.py`) that widens `processed_events` (`event_id` UUID→Text; adds `payload_hash`/`response_status`/`response_body`/`state`) and changes `payments.amount` Float→`NUMERIC(11,2)`. Downgrade the DB only after confirming no non-UUID `event_id` values exist; the downgrade removes checkout metadata, casts UUID-compatible event IDs back, and restores Float. Deploy the migration **before** the route; reverse in the opposite order (app, then DB).

## Dependencies

- Existing on-disk infra: `ProcessedEventStore`, `SqlAlchemyOutboxRepository`, `EventEnvelope`, DI containers, the 3-state `Order`.
- Alembic migration required (deploy before route): durable `processed_events` response-cache columns + `state`; `payments.amount` Float→`NUMERIC(11,2)`.
- PostgreSQL required for the migration-constraint and `pg_advisory_xact_lock` integration tests; unit tests stay DB-free. No RabbitMQ.

## Success Criteria

- [ ] `POST /api/v1/checkout` confirms an order only when inventory reserved **and** payment approved.
- [ ] Payment declined after reservation releases inventory and cancels exactly once.
- [ ] Same `Idempotency-Key` + payload replays without double-charge/double-reserve; differing payload → `409`.
- [ ] Same `(order_id, amount, currency)` always yields the same authorization result.
- [ ] ADR 0005 status reads "Accepted (current implementation)".
- [ ] All four modules connected in one happy-path HTTP/integration test.

---

Revision 2 (post-design consistency correction): Rollback/Dependencies/Affected Areas now acknowledge the design-selected Alembic migration (`..._extend_checkout_idempotency.py`) and app-first rollback ordering; likely slices 2→3 to match the design's migration/idempotency boundary; replay-cache Key Contract and risk row updated to the resolved durable-cache decision. Approved scope, capabilities, success criteria, and the A1+B3+C1+P2 combination are unchanged.
