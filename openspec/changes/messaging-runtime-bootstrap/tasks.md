# Tasks: Messaging Runtime Bootstrap

## Review Workload Forecast

Review budget: 800 changed lines (session override). Estimated changed lines (authored): ~1,700–2,600. Delivery strategy: auto-chain.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

auto-chain; chain strategy resolved by user: stacked-to-main — PR 1 → PR 4 each merge to main in order, each slice independently reviewable; retarget/rebase any child diff showing prior-PR changes.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Outbox durability + payload + index | PR 1 | `uv run pytest backend/app/tests/shared/messaging/` | Postgres: disjoint claims, EXPLAIN | Revert migration + messaging changes |
| 2 | Consumer registry + lifespan | PR 2 | `uv run pytest backend/app/tests/runtime/` | uvicorn, broker down, /health 200 | Revert runtime files + app.py + settings |
| 3 | Handlers + guards + notification | PR 3 | `uv run pytest backend/app/tests/modules/{inventory,orders,notifications}/application/` | fake-message tests | Revert handlers + container wiring |
| 4 | E2E + integration + CI + docs | PR 4 | `EVENTCOMMERCE_RUN_RABBITMQ_INTEGRATION=1 uv run pytest backend/app/tests/integration/` | docker compose RabbitMQ | Revert CI/env/docs only |

## Phase 1: Foundation

- [x] 1.1 Correct `specs/project-foundation-docs/spec.md`: `InventoryRejected`/`OrderConfirmed`/`OrderCancelled` → Current Events (delivered-evidence); no AMQP-live claim pre-ship.
- [x] 1.2 RED→GREEN `create_order.py` + test: `OrderCreated` row carries `customer_id` + `items` (API + checkout).
- [x] 1.3 Migration `alembic/versions/<rev>_index_pending_outbox.py` (head `8d9e0f1a2b3c`): additive `(status, created_at)` index; downgrade drops.
- [x] 1.4 RED→GREEN `outbox_repository.py` + test: `get_pending` claims `FOR UPDATE SKIP LOCKED`, ordered, capped; disjoint workers.
- [x] 1.5 RED→GREEN `outbox_worker.py` + test: publish failure leaves row pending + logs + continues; publish only after confirm.

## Phase 2: Runtime bootstrap

- [x] 2.1 RED→GREEN `rabbitmq_publisher.py` + test: PERSISTENT, `message_id`, `event_type`/`aggregate_id` headers; never log payloads.
- [x] 2.2 RED→GREEN `shared/messaging/consumer.py` + test: registry validation; durable, prefetch 1; unknown/malformed acked; failure nack requeue.
- [x] 2.3 RED→GREEN `messaging_runtime.py` + `backend/app/tests/runtime/`: broker-down startup healthy, backoff (cap 30s); shutdown cancels scheduler, closes ≤10s.
- [x] 2.4 GREEN `app.py` lifespan: non-fatal connect; start/stop runtime ordering.
- [x] 2.5 GREEN `settings.py` + `.env.example`: `EVENTCOMMERCE_RABBITMQ_*` vars, poll interval, batch size.

## Phase 3: Idempotent handlers

- [x] 3.1 RED→GREEN `inventory/application/order_status.py` (`OrderStatusQuery`) + `get_order_status.py` + guard in `process_inventory_reservation.py` + test: terminal skip; duplicate once; no sync-checkout double reserve.
- [x] 3.2 RED→GREEN guard `process_inventory_result.py` + test: late result on confirmed/cancelled no-ops, skip recorded.
- [x] 3.3 RED→GREEN `notifications/application/process_order_notification.py` + test: notifies once; duplicate no-op; processed row same transaction.
- [x] 3.4 GREEN wire containers (orders/inventory/notifications); composition supplies `GetOrderStatus`.

## Phase 4: Chain, integration, CI, docs

- [x] 4.1 RED→GREEN chain e2e `test_chain_e2e.py` (runtime/): fake publisher, order→inventory→terminal; no broker in default suite.
- [ ] 4.2 GREEN gated integration test `test_rabbitmq_integration.py` (integration/, skip unless env set): restart persistence, topology recovery, EXPLAIN evidence.
- [ ] 4.3 GREEN `.github/workflows/api-ci.yml`: rabbitmq service, gated env, integration job.
- [ ] 4.4 GREEN docs (after 2.4): `ARCHITECTURE.md` matrix `implemented` + evidence; GLOSSARY wiring; ADR 0002 delivered; README snapshot; no premature AMQP claims.
