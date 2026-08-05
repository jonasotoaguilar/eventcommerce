# Tasks: Checkout End-to-End (Synchronous Orchestrator)

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High
800-line budget risk: High

## Review Workload Forecast

Estimated changed lines: ~1,800–2,500 (additions+deletions, incl. tests). Delivery strategy: auto-chain. Suggested split: S1 Migration+idempotency → S2 Decimal payment+ADR → S3 Inventory lock+Checkout+API+E2E → Chore stub deletion. `chain_strategy: feature-branch-chain` (user-selected 2026-08-03: automatic chained PRs, 800-line review budget).

### Spec Scenario → Task Traceability (all 12, none omitted)

| # | Spec Scenario | Task(s) |
|---|---|---|
| 1 | Valid request proceeds | 3.4 RED (positive case), 3.13 GREEN |
| 2 | Invalid quantity or empty items rejected | 3.4 RED, 3.13 GREEN |
| 3 | Happy path confirms the order | 3.5 RED, 3.14 GREEN |
| 4 | Exactly one terminal transition (ownership) | 3.20 RED, 3.19 REFACTOR |
| 5 | Insufficient stock cancels | 3.7 RED, 3.3+3.14 GREEN |
| 6 | Payment declined releases inventory and cancels | 3.6 RED, 3.14 GREEN |
| 7 | Determinism across evaluations | 2.1 RED (dedicated assertion block) |
| 8 | Missing key executes per request | 3.8 RED, 3.14 GREEN |
| 9 | Replay returns cached response | 3.9 RED, 1.7 GREEN |
| 10 | Key reused with differing payload conflicts | 3.10 RED, 1.7 GREEN |
| 11 | Concurrent duplicates isolate | 3.11 RED, 1.7 GREEN |
| 12 | Status and notification mapping | 3.12 RED, 3.18 GREEN |

### Suggested Work Units

| Unit | Goal | Focused test command | Runtime harness | Rollback boundary |
|------|------|----------------------|-----------------|-------------------|
| S1 | Migration + idempotency/concurrency | `cd backend && uv run python -m pytest app/tests/test_processed_event_store_migration.py -x` | Postgres test DB (conftest.py); no AMQP | Revert alembic rev; revert `ProcessedEventModel` + `ProcessedEventStore` |
| S2 | Decimal payment policy + failure + ADR | `cd backend && uv run python -m pytest app/modules/payments/tests/test_payment_policy.py -x` | N/A (DB-free unit) | Revert `policy.py`; restore `random.choice`; revert ADR status; keep S1 migration |
| S3 | Inventory lock + Checkout/DI/API + E2E | `cd backend && uv run python -m pytest app/tests/test_checkout_end_to_end.py -x` | Postgres test DB; `uv run uvicorn app.main:app` + `curl POST /api/v1/checkout` | Revert `app/modules/checkout/*`; revert `app.py` router; revert FOR UPDATE; keep S1+S2 |
| Chore | Dead stub deletion (isolated) | `cd backend && uv run python -m pytest -x` | N/A (file-only) | Restore `repositories/sqlalchemy_repository.py`; no schema/imports affected |

Chain ordering (feature-branch-chain): PR #1 (S1) targets the tracker branch `feat/checkout-end-to-end`; S2 targets the S1 PR branch; S3 targets the S2 PR branch; Chore targets `main` after S3 integrates. `chain_strategy: feature-branch-chain` — user-selected automatic chained PRs (2026-08-03); 800-line review budget.

## Phase 1: Slice 1 — Migration + Idempotency (Foundation)

- [x] 1.1 RED: migration test — `event_id` UUID→Text, `payload_hash CHAR(64)`, `response_status`, `response_body JSON`, `updated_at`, `state` (`processed|in_progress|completed`), backfill `state='processed'`; `payments.amount` Float→`NUMERIC(11,2)`.
- [x] 1.2 RED: payload-hash canonicalization (sorted-key compact JSON, item order preserved, deterministic).
- [x] 1.3 RED: `pg_advisory_xact_lock` race — identical concurrent payloads execute once; differing payload under in-use key → `409` without mutating first execution.
- [x] 1.4 RED: replay — cached `response_status`+`response_body` returned, no re-execution.
- [x] 1.5 GREEN: `backend/alembic/versions/*_extend_checkout_idempotency.py` (deploy before route; downgrade documented).
- [x] 1.6 GREEN: update `backend/app/shared/messaging/models.py` (`ProcessedEventModel`).
- [x] 1.7 GREEN: extend `backend/app/shared/messaging/idempotency.py` — `claim`/`complete_with_response`/`fetch_cached`/`release_claim`; advisory-lock helper; 16 KiB cap; rollback removes uncommitted claim.
- [x] 1.8 REFACTOR: extract `canonicalize_request` + `payload_hash` helpers.

## Phase 2: Slice 2 — Decimal Payment Policy + Failure + ADR

- [x] 2.1 RED: payment vectors + determinism — assert each tuple yields the same first digest byte across N=1000 evaluations and matches the verified fixtures:
  - V1 `00000000-0000-0000-0000-000000000001|19.99|USD` (UTF-8) → SHA-256 byte 0 = `0x12` (decimal 18, < 192 → approved).
  - V2 `00000000-0000-0000-0000-000000000001|0.00|USD` (UTF-8) → byte 0 = `0xc9` (decimal 201, ≥ 192 → declined).
  - V3 `00000000-0000-0000-0000-000000000001|19.90|USD` (canonical from `19.9`, UTF-8) → byte 0 = `0x09` (decimal 9, approved).
  - V4 `00000000-0000-0000-0000-000000000001|999.99|EUR` (UTF-8) → byte 0 = `0x27` (decimal 39, approved).
  - V5 `00000000-0000-0000-0000-000000000001|0.01|GBP` (UTF-8) → byte 0 = `0xd8` (decimal 216, declined).
  - V6 `ffffffff-ffff-ffff-ffff-ffffffffffff|19.99|USD` (UTF-8) → byte 0 = `0x34` (decimal 52, approved) — different order_id, same outcome class as V1 (proves order_id is in the digest).
- [x] 2.2 RED: `ProcessPaymentFailure` — persists `declined` Payment with `failure_reason`; does NOT mutate order.
- [x] 2.3 RED: `Decimal` amount validation — rejects >2 decimals and negatives.
- [x] 2.4 GREEN: `backend/app/modules/payments/domain/policy.py` (`is_payment_approved`, threshold 192, UTF-8 canonical bytes, threshold as module constant).
- [x] 2.5 GREEN: update `AuthorizePayment.execute` to call policy; persist `amount: Decimal`; remove `random.choice`.
- [x] 2.6 GREEN: update `PaymentModel.amount`→`Numeric(11,2)`; repo to `Decimal`.
- [x] 2.7 GREEN: implement `ProcessPaymentFailure.execute` to persist `declined` Payment (do NOT cancel).
- [x] 2.8 REFACTOR: update `docs/adr/0005-use-deterministic-simulated-payments.md` status → "Accepted (current implementation)".

## Phase 3: Slice 3 — Inventory Lock + Checkout + API + E2E

- [x] 3.1 RED: `SELECT FOR UPDATE` sorted by `product_id`, deadlock-free under concurrent multi-line reserves; insufficient stock raises with no partial reservation.
- [x] 3.2 RED: rollback after later persistence error undoes original reservation.
- [x] 3.3 GREEN: add `lock_and_check_availability` to `backend/app/modules/inventory/infrastructure/sqlalchemy_repository.py`; sort+lock+check before mutate; `ReleaseInventory` compensates.
- [x] 3.4 RED: `CheckoutRequest` validation — `422` for `quantity=0`, `items=[]`, invalid currency (syntactic ISO 4217, three uppercase ASCII letters; not a catalog check), `amount` with >2 decimals, missing fields; `201`-class pass-through for a fully-valid request.
- [x] 3.5 RED: happy path — `201`, `pending→confirmed`, `approved` Payment, inventory reserved, outbox rows, notification intent.
- [x] 3.6 RED: payment decline — release, cancel `payment_declined`, `PaymentFailed` persisted, no double-charge, cancellation notification.
- [x] 3.7 RED: insufficient stock — cancel `insufficient_stock`, no `approved` Payment, cancellation notification.
- [ ] 3.8 RED: missing `Idempotency-Key` — two identical requests produce two distinct orders.
- [ ] 3.9 RED: replay — cached original status+body, no re-execution.
- [ ] 3.10 RED: key/payload mismatch — `409`, first execution intact.
- [ ] 3.11 RED: concurrent duplicate — exactly one execution, identical terminal response.
- [ ] 3.12 RED: notification — intent at every terminal state; post-commit `SendOrderNotification` failure does NOT roll back.
- [x] 3.13 GREEN: `backend/app/modules/checkout/api/schemas.py` — `CheckoutRequest`: `customer_id`/`product_id` 1–128 chars, 1–100 unique items, `quantity` 1–10,000, `amount: Decimal` 0–999,999,999.99 with ≤2 decimals, `currency` three uppercase ASCII letters (syntactic ISO 4217 — does NOT prove currency existence; catalog/reconciliation deferred); optional `Idempotency-Key` 1–128 visible ASCII. `CheckoutResponse` carries `order_id`/`status`/nullable `cancel_reason`/nullable `payment_status`.
- [x] 3.14 GREEN: `backend/app/modules/checkout/application/checkout.py` — one tx: claim→create order→lock+reserve→authorize+persist→confirm OR release+cancel→cache→COMMIT→best-effort notify in separate tx.
- [x] 3.15 GREEN: `backend/app/modules/checkout/api/container.py` — request-local `AsyncSession`; wires all repos + use cases.
- [x] 3.16 GREEN: `backend/app/modules/checkout/api/routes.py` — `POST /api/v1/checkout` maps 201/422/409/500.
- [x] 3.17 GREEN: wire `OrdersContainer` with `ConfirmOrder`+`CancelOrder`+`ProcessOrderInventoryResult`; populate `PaymentsContainer` with `payment_repo`, `AuthorizePayment`, `ProcessPaymentFailure`.
- [x] 3.18 GREEN: include `checkout_router` in `backend/app/app.py` under `/api/v1`; structured logging `checkout_started/completed/replayed/conflict/rolled_back/notification_failed` with key-hash prefix only.
- [x] 3.19 REFACTOR: extract `serialize_response`+`hash_key` helpers; assert `ProcessOrderInventoryResult` NOT invoked synchronously; verify `cancel_reason` set exactly once.
- [x] 3.20 RED: single-terminal-transition ownership — for any checkout reaching a terminal state, assert exactly one terminal status mutation and final state is `confirmed` OR `cancelled` (never both, never twice); inner use cases do NOT mutate `status` or `cancel_reason`; verified by spying `Order.confirm`/`Order.cancel`.

## Phase 4: Slice 4 — Dead Stub Chore (Isolated)

- [ ] 4.1 Verify zero production import of `backend/app/modules/orders/infrastructure/repositories/sqlalchemy_repository.py` (grep across `app/`).
- [ ] 4.2 Delete the file; full suite green.

## Out of Scope
Catalog, cart, IAM, AMQP consumer/scheduler/lifespan, 5-state order machine, confirm/cancel HTTP, stale-docs realignment. Threat matrix rows all N/A per design. Currency allowlist (e.g. `USD|EUR|GBP`) is NOT a task — checkout accepts syntactic ISO 4217 only; existence/allowlist reconciliation is a catalog follow-up.
