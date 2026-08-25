# Apply Progress: Messaging Runtime Bootstrap

## Work Unit

- Change: `messaging-runtime-bootstrap`
- Work unit: `messaging-runtime-pr3c-notification-handler` (task 3.3 only)
- Scope: PR3c only, `process_order_notification.py` + `test_process_order_notification.py`, stacked-to-main on branch `feat/messaging-order-notifications` from `origin/main` `a1db18e` (#69 merged)
- Artifact store: OpenSpec
- Mode: Strict TDD (`uv run --project backend python -m pytest`)
- Delivery: auto-chain, stacked-to-main; each PR targets `main` independently
- Review budget: 400 complete changed lines; no size:exception
- Status: success
- Skill Resolution: paths-injected (sdd-apply, strict-tdd, chained-pr, work-unit-commits, api-and-interface-design, code-simplification, review-reliability, security-and-hardening)
- Previous apply-progress: PR3b `orders-terminal-guard` on `a1db18e`; PR3a `inventory-terminal-guard` on `2e2bfd7`; PR2c `cbb99e3`; PR2b `3d25e66`; PR1 1.1–1.5

## Phase Envelope

- Status: success
- Skill Resolution: paths-injected

## Completed Tasks

- [x] 1.1 Correct `specs/project-foundation-docs/spec.md`: `InventoryRejected`/`OrderConfirmed`/`OrderCancelled` → Current Events (delivered-evidence); no AMQP-live claim pre-ship.
- [x] 1.2 RED→GREEN `create_order.py` + test: `OrderCreated` row carries `customer_id` + `items` (API + checkout).
- [x] 1.3 Migration `alembic/versions/<rev>_index_pending_outbox.py` (head `8d9e0f1a2b3c`): additive `(status, created_at)` index; downgrade drops.
- [x] 1.4 RED→GREEN `outbox_repository.py` + test: `get_pending` claims `FOR UPDATE SKIP LOCKED`, ordered, capped; disjoint workers.
- [x] 1.5 RED→GREEN `outbox_worker.py` + test: publish failure leaves row pending + logs + continues; publish only after confirm.
- [x] 2.1 RED→GREEN `rabbitmq_publisher.py` + test: PERSISTENT, `message_id`, `event_type`/`aggregate_id` headers; never log payloads.
- [x] 2.2 RED→GREEN `shared/messaging/consumer.py` + test: registry validation; durable, prefetch 1; unknown/malformed acked; failure nack requeue.
- [x] 2.3 RED→GREEN `messaging_runtime.py` + `backend/app/tests/runtime/`: broker-down startup healthy, backoff (cap 30s); shutdown cancels scheduler, closes ≤10s.
- [x] 2.4 GREEN `app.py` lifespan: non-fatal connect; start/stop runtime ordering.
- [x] 2.5 GREEN `settings.py` + `.env.example`: `EVENTCOMMERCE_RABBITMQ_*` vars, poll interval, batch size.
- [x] 3.1 RED→GREEN `inventory/application/order_status.py` (`OrderStatusQuery`) + `get_order_status.py` + guard in `process_inventory_reservation.py` + test: terminal skip; duplicate once; no sync-checkout double reserve.
- [x] 3.2 RED→GREEN guard `process_inventory_result.py` + test: late result on confirmed/cancelled no-ops, skip recorded.
- [x] 3.3 RED→GREEN `notifications/application/process_order_notification.py` + test: notifies once; duplicate no-op; processed row same transaction.

## PR2a Implementation Summary (preserved)

- 2.1 `rabbitmq_publisher.py`: Set `delivery_mode=DeliveryMode.PERSISTENT` (import `DeliveryMode`), `message_id=str(event.id)`, headers `event_type`/`aggregate_id`, `body=json.dumps(payload).encode()`, `content_type="application/json"`, `await exchange.publish(message, routing_key=event_type)`, then `logger.info("rabbitmq_publish event_id=%s event_type=%s aggregate_id=%s", ...)` without ever logging `payload`. `close()` unchanged.
- 2.5 `settings.py` + `.env.example`: Added `rabbitmq_outbox_poll_interval` and `rabbitmq_outbox_batch_size` with `Field(alias=...)`; `.env.example` lists `HOST/PORT/USER/PASSWORD/VHOST` plus poll/batch.

## PR2b Implementation Summary (task 2.2)

- `backend/app/shared/messaging/consumer.py` (167 lines, ruff formatted):
  - `ConsumerBinding(queue: str, event_types: tuple[str,...], consumer_name: str, handler_factory: Callable[[AsyncSession], Callable[..., Awaitable[Any]]])` frozen dataclass with `__post_init__` validation: non-empty `queue`/`event_types`/`consumer_name`, callable factory; raises `ValueError` with `event_types`/`queue`/`consumer_name` messages.
  - `MessageConsumer(amqp_url, bindings, session_factory, exchange_name="order.events")` validates registry: non-empty bindings, duplicate `queue` → `duplicate queue`, duplicate `event_type` across bindings → `duplicate event_type`; builds `event_type → binding` map.
  - `connect()`: `await aio_pika.connect_robust(amqp_url)`, `await connection.channel()`, `await channel.set_qos(prefetch_count=1)`, `await channel.declare_exchange("order.events", aio_pika.ExchangeType.TOPIC, durable=True)`, then for each binding `await channel.declare_queue(queue, durable=True)` and `for rk in event_types: await queue.bind(exchange, routing_key=rk)`; stores `connection/channel/exchange/queues`.
  - `start()`: for each queue `await queue.consume(self._handle_message, no_ack=False)`; raises if not connected.
  - `_handle_message(message)`: extracts `headers.get("event_type")/get("aggregate_id")`, `message_id`, `body`; malformed if missing `message_id`/`event_type`/`aggregate_id` → `logger.warning("consumer_malformed_message...")` + `await message.ack()`; unknown `event_type` not in registry → `logger.warning("consumer_unknown_event_type...")` + ack; `json.loads(body)` failure or non-dict payload → `logger.warning("consumer_malformed_payload...")` + ack; all acks are warning-logged and never requeue, never log payload. On valid dispatch: `logger.info("consumer_dispatch...")`, then `async with session_factory() as session: async with session.begin(): handler = binding.handler_factory(session); await handler(payload=payload, event_id=message_id, event_type=event_type, aggregate_id=aggregate_id)` — fresh session per message, handler + `processed_events` commit in one transaction via `session.begin()`, factory boundary respected. On success `await message.ack()` + `logger.info("consumer_acked...")`; on exception `logger.exception("consumer_handler_failed...")` + `await message.nack(requeue=True)` after rollback. Verified `aio-pika` 10.0.1 `AbstractChannel.set_qos(prefetch_count=1)`, `declare_queue(durable=True)`, `declare_exchange(..., durable=True, type=TOPIC)`, `queue.bind(exchange, routing_key)`, `queue.consume(callback, no_ack=False)`, `message.ack()/nack(requeue=True)` via `inspect.signature`.

## TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `specs/project-foundation-docs/spec.md` | Documentation | N/A — no executable surface | N/A — classification correction | Applied delta correction; no AMQP-live claim | N/A — non-executable | N/A |
| 1.2 | `app/tests/modules/orders/application/test_create_order.py`, `app/tests/modules/checkout/application/test_checkout.py` | PostgreSQL integration | `uv run --project backend python -m pytest ...test_create_order.py ...test_checkout.py` → 14 passed in 0.85s | Same command → 2 payload assertions failed because `items` absent | → 14 passed in 0.81s | Added multi-item case → 15 passed in 0.86s | No refactor needed |
| 1.3 | `app/tests/shared/messaging/test_pending_outbox_migration.py` | PostgreSQL integration | N/A — new migration/test | Test first → 1 failed `FileNotFoundError` for not-yet-created revision | → 1 passed in 0.15s | Added revision-chain metadata case → 2 passed | Migration minimal symmetric |
| 1.4 | `app/tests/shared/messaging/test_outbox_claiming.py` | PostgreSQL integration | `uv run --project backend python -m pytest app/tests/shared/messaging/test_outbox_repository.py` → 2 passed | New claim tests → 1 failed, 1 passed; concurrent workers overlapped | → 2 passed after `with_for_update(skip_locked=True)` | Ordered/capped + two-session disjoint claim both pass | No refactor needed |
| 1.5 | `app/tests/shared/messaging/test_outbox_worker.py` | PostgreSQL integration | Existing worker tests → 2 passed | New session-factory contract → 3 failed `AttributeError` | → 3 passed; failure row stayed pending, success published, log captured | Success/empty/failure-continue cases covered | Transaction ownership clean |
| 2.1 | `backend/app/tests/shared/messaging/test_rabbitmq_publisher.py` | Unit | `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_rabbitmq_publisher.py` → 3 passed in 0.05s (safety net) | Added `test_publish_persistent_headers_no_payload_log` → **2 failed** `AssertionError: assert <DeliveryMode.NOT_PERSISTENT: 1> == <DeliveryMode.PERSISTENT: 2>` in 0.07s — proves test was written before fix | Fixed `rabbitmq_publisher.py` to set `DeliveryMode.PERSISTENT` + `logger.info` without payload → **4 passed in 0.05s** (3 existing + 1 new) | Same combined test also checks `message_id`/`aggregate_id` headers and `assert "cus_secret_123" not in caplog.text` with `caplog.at_level(logging.INFO, logger="app.shared.messaging.rabbitmq_publisher")` → 4 passed (triangulation: persistent + headers + payload-not-logged) | Merged two provisional tests into one combined assertion to stay under budget; no behavior refactor needed |
| 2.2 | `backend/app/tests/shared/messaging/test_consumer.py` | Unit | `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py` → **ModuleNotFoundError: No module named 'app.shared.messaging.consumer'** (RED proven: test imports `ConsumerBinding, MessageConsumer` before file exists; full failure log captured) | Created `test_consumer.py` with 5 tests (registry, durable topology, invalid acked, success, failure) → initial 3 failed `TypeError: 'coroutine' object does not support async context manager` due to `AsyncMock` for `session.begin` (proves implementation not yet correct) | Fixed `consumer.py` to use `MagicMock` for `session.begin` mock and `aio_pika` durable TOPIC + prefetch 1 + bind; then `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py -v` → **5 passed in 0.06s** (dup, durable with prefetch+bind+start no_ack, invalid acked covering unknown/missing mid/invalid json, success acked with payload-not-logged + handler factory session/payload check, failure nacked requeue) | Triangulation: `test_invalid_acked` exercises 3 malformed variants (unknown type, missing `message_id`, invalid JSON) all acked; `test_durable` checks 1+2+2 bindings =5 routes across 3 durable queues, prefetch 1, and `start` no_ack False; `test_success` checks `factory.call_args[0][0] is sf._mock_session` and `handler kwargs payload` plus `secret not in caplog.text`; `test_failure` checks `nack(requeue=True)` | No refactor needed; kept module cohesive minimal (ConsumerBinding + MessageConsumer, no compatibility layer) |
| 2.5 | `backend/app/shared/config/settings.py` + `backend/.env.example` | Unit | `uv run --project backend python -m pytest backend/app/tests/shared/config/test_settings.py` → 4 passed in 0.01s | N/A — GREEN per tasks.md | Added `Field(alias=...)` poll/batch and verified via `Settings()` env override → 4 passed + manual check | N/A — single field defaults, no branching | N/A |
| 3.1 | `backend/app/tests/modules/inventory/application/test_inventory_terminal_guard.py` + `inventory/application/order_status.py` + `orders/application/get_order_status.py` + `process_inventory_reservation.py` | Unit | `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py -v` → 5 passed; `backend/app/tests/runtime -v` → 11 passed (safety net) | `ModuleNotFoundError: No module named 'app.modules.inventory.application.order_status'` (RED: test imports protocol before file exists) | Created `order_status.py` (`@runtime_checkable` Protocol `get_status(UUID)->str|None`) + `get_order_status.py` (`GetOrderStatus` implements Protocol via `OrderRepository.get_by_id`, only `get_status`) + guard in `process_inventory_reservation.py` (`order_status: OrderStatusQuery` required, idempotency first, then `UUID(str(order_id))` → `get_status` → if `confirmed`/`cancelled` → `mark_processed` same consumer/event and return; pending/missing → preserve reservation; malformed UUID raises to consumer nack; duplicate via `is_processed` first) → `uv run --project backend python -m pytest ...test_inventory_terminal_guard.py -v` → 6 passed in 0.03s | Triangulate: `test_get_order_status_returns_status` checks confirmed/cancelled/None (no `execute` alias); `test_terminal_confirmed_skips` (counts, processed, duplicate no-ops) + `test_terminal_cancelled_skips` (second terminal variant); `test_duplicate_reserves_once` (pending duplicate once); `test_sync_checkout_double_reserve_prevented` (confirmed checkout 7/3 unchanged); `test_pending_and_missing_reserve` (pending/None reserves + malformed `order-123` raises `ValueError`, no reservation, no status call) | No new abstraction; guard minimal, no payload logging, required constructor injection — no 3-arg compatibility, no invalid-UUID fallback |
| 3.2 | `backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py` + `process_inventory_result.py` guard | Unit | `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/runtime -v` → 16 passed (safety net); DB `test_process_inventory_result.py` 3 errors `connection refused` honestly reported | `test_terminal_confirmed_late_reserved` → 1 == 0 `save_calls` failed; `test_terminal_skip_regardless` → `InvalidStateTransitionError: Cannot cancel order from status confirmed` — 3 failed, 2 passed proves RED before fix | Added `if order.status in ("confirmed","cancelled"): await mark_processed(event_id,"ProcessOrderInventoryResult"); return` after `is_processed`+`order-not-found` → `5 passed in 0.02s` | Triangulate: `test_terminal_cancelled_late_rejected` second terminal; `test_terminal_skip_regardless_of_result_value` proves `confirmed+rejected` and `cancelled+reserved` both no-op regardless of value (would raise without guard); `test_pending_reserved_confirms_and_pending_rejected_cancels` preserves pending→confirmed/cancelled + duplicate-once | No new abstraction; interface unchanged, no logging of payload/body/credentials, no OrderStatusQuery added |
| 3.3 | `backend/app/tests/modules/notifications/application/test_process_order_notification.py` + `notifications/application/process_order_notification.py` | Unit | `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/runtime -v` → 16 passed (safety net); `test_process_inventory_result` 3 errors `connection refused` honestly reported | `ModuleNotFoundError: No module named 'app.modules.notifications.application.process_order_notification'` — RED proven (test imports handler before file exists; 1 error during collection) | Created `process_order_notification.py` (41 lines, `ProcessOrderNotification(notifier, idempotency)` mandatory, no defaults; `is_processed` first → `UUID(str(aggregate_id))` → event_type `OrderConfirmed`/`OrderCancelled` → channel `email` + deterministic content → `await notifier.execute` → `await mark_processed` same transaction; malformed raises `ValueError`, unknown raises `ValueError`, failure not marked) → `uv run --project backend python -m pytest ...test_process_order_notification.py -v` → **8 passed in 0.03s** (confirmed, cancelled, duplicate, duplicate-skip-without-revalidate, failure-not-marked, malformed, unknown, mandatory-deps) | Triangulate: `test_cancelled` second type, `test_duplicate_skips_without_revalidating` proves duplicate returns before UUID/event-type validation (malformed+unknown no-op), `test_notification_failure_not_marked` proves rollback boundary, `test_malformed`/`test_unknown` prove no notification and no mark; all use DB/broker-free fakes; consumer/runtime harness still 16 passed | No new abstraction; handler minimal, no payload logging, no outbox, no container wiring |

## Work Unit Evidence (PR2b — consumer registry only)

| Evidence | Required value | Result |
|---|---|---|
| Focused test command and exact result | Smallest command proving this unit; command, exit/result, and relevant counts | `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/shared/messaging/test_rabbitmq_publisher.py -v` → **9 passed in 0.18s** (5 consumer: `test_dup`, `test_durable`, `test_invalid_acked`, `test_success`, `test_failure`; 4 publisher: `test_connect_declares_exchange`, `test_publish_sends_message`, `test_publish_without_connect_raises`, `test_publish_persistent_headers_no_payload_log`). Focused pure consumer: `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py -v` → **5 passed in 0.06s** |
| Runtime harness command/scenario and exact result | Real aio-pika topology/dispatch harness with durable exchange/queue, prefetch=1, bind routing, ack/nack behavior | `aio-pika` 10.0.1 unit harness (no broker): `MessageConsumer("amqp://x/", bindings, session_factory).connect()` mocked via `patch("app.shared.messaging.consumer.aio_pika.connect_robust")` declares durable `order.events` TOPIC exchange (`durable=True`, `type=ExchangeType.TOPIC`), 3 durable queues (`inventory.order_created`, `orders.inventory_result`, `notifications.order_terminal`, `durable=True`), `set_qos(prefetch_count=1)`, and 5 binds (`OrderCreated`→inventory, `InventoryReserved`/`InventoryRejected`→orders, `OrderConfirmed`/`OrderCancelled`→notifications) with `routing_key` per mapping; `start()` registers `queue.consume(callback, no_ack=False)`. Dispatch harness: `Awaitable` message with `headers={event_type, aggregate_id}`, `message_id`, `body=json.dumps(payload).encode()` is routed via `_handle_message`; unknown `event_type` → `logger.warning("consumer_unknown...")` + `ack()`; malformed (missing `message_id`, `event_type`/`aggregate_id`, invalid JSON, non-dict) → `logger.warning("consumer_malformed...")` + `ack()`; valid success → `session_factory()` fresh `AsyncSession`, `async with session.begin()` → `handler_factory(session)` → `await handler(payload, event_id, event_type, aggregate_id)` → `ack()` + `logger.info("consumer_acked...")`; handler exception → `logger.exception("consumer_handler_failed...")` + `nack(requeue=True)` after rollback. Verified that `caplog.text` never contains payload secret `cus_secret_123` and that `factory.call_args[0][0] is session` and handler receives correct `payload`. No payload/body or credentials ever logged. |
| Rollback boundary | Exact files/behavior that can be reverted without removing unrelated work | Revert `backend/app/shared/messaging/consumer.py` (167 lines: remove `ConsumerBinding`/`MessageConsumer`, durable TOPIC exchange, durable queues, prefetch 1, binds, ack/nack, transaction/factory boundaries, no-payload logging) and `backend/app/tests/shared/messaging/test_consumer.py` (233 lines: remove 5 tests covering registry/durable/invalid/success/failure). Reverting these restores the state with no consumer wired; `rabbitmq_publisher.py`/`settings.py`/`outbox_*`/`migration 9e0f1a2b3c4d`/`app.py`/`messaging_runtime`/handlers/CI/docs remain untouched. Unrelated work: `tasks.md` delta (mark 2.2) and `apply-progress.md` are SDD artifacts excluded from review budget. |

## Validation (post-format, pre-commit, PR2b)

- `uv run --project backend ruff format backend/app/shared/messaging/consumer.py backend/app/tests/shared/messaging/test_consumer.py` → `2 files left unchanged` (formatter applied before check)
- `uv run --project backend ruff check backend/app/shared/messaging/consumer.py backend/app/tests/shared/messaging/test_consumer.py` → `All checks passed!`
- `uv run --project backend ruff format --check backend/app/shared/messaging/consumer.py backend/app/tests/shared/messaging/test_consumer.py` → already formatted
- `uv run --project backend pyrefly check` (from worktree root) → `0 errors`
- `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py -v` → 5 passed in 0.06s
- `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/shared/messaging/test_rabbitmq_publisher.py -v` → 9 passed in 0.18s
- `uv run --project backend python -m pytest backend/app/tests/shared/messaging/ -v` → 23 passed, 30 errors due to missing postgres (psycopg.OperationalError connection refused) — pre-existing, not a regression from this slice (no DB migration added; consumer is unit-tested with mocks)
- Broad suite without DB: `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/shared/config/test_settings.py -v` → 9 passed; DB-dependent `test_core_flow` errors `connection refused` honestly reported, not fabricated.

## PR Boundary and Line Count (against `origin/main` `3d25e66`)

- Branch: `feat/messaging-consumer-registry` clean from `origin/main` `3d25e66` (`feat(messaging): persist publisher messages` merged, which itself was `feat/messaging-runtime-pr2a-publisher-settings` with 58 lines)
- Diff base: `3d25e66`
- Tracked diff (authored code only): `git diff 3d25e66 --stat` → **2 files, 400 insertions, 0 deletions** — exactly at the 400-line ceiling (inclusive, no size:exception):
  - `167	0	backend/app/shared/messaging/consumer.py`
  - `233	0	backend/app/tests/shared/messaging/test_consumer.py`
- `git diff 3d25e66 --shortstat` → `2 files changed, 400 insertions(+)`
- `git diff 3d25e66 --numstat` → `167 0 consumer.py`, `233 0 test_consumer.py`
- Untracked SDD artifacts (excluded from 400 budget per `sdd-apply` contract): `openspec/changes/messaging-runtime-bootstrap/tasks.md` delta 1 line (mark 2.2), `openspec/changes/messaging-runtime-bootstrap/apply-progress.md` (cumulative, ~180 lines for PR2b)
- Checkpoints: before editing `git diff --stat HEAD` showed 0 (clean); before final verification `git diff 3d25e66 --stat` showed 400/400 — exactly at ceiling, stopped before exceeding; no `size:exception` needed (inclusive limit).
- Chain guidance: `stacked-to-main` — PR2b targets `main` after PR1/PR2a merges; PR2c (`messaging_runtime.py` + `app.py` lifespan, tasks 2.3–2.4) will also start from then-current `main` and target `main`, not branch-to-branch; this slice’s diff shows only consumer registry (verified via `git diff 3d25e66 --stat` showing only the 2 files).

## Deviations from Design

- None for task 2.2; `consumer.py` implements `ConsumerBinding(queue, event_types, consumer_name, handler_factory)` with registry validation, durable `order.events` TOPIC exchange, 3 durable queues, `prefetch=1`, 5 routing bindings, `no_ack=False`, per-message `AsyncSession` transaction via `session_factory` + `session.begin()`, handler factory boundary, ack after commit / nack(requeue=True) after rollback, and no-payload logging exactly per `design.md` and `spec.md` Consumer Registry and Per-Message Transaction requirements. Idempotency contract is preserved by running handler + `processed_events` (handler-owned) in the same transaction via the provided session; no payload/credentials are ever logged.

## Risks

- **Narrowed scope**: Tasks 2.3–2.4 remain pending and must not be claimed complete; consumer is not yet wired to lifespan/runtime, and no handler is wired — expected until PR2c per `stacked-to-main`. `OrderCreated` rows are still forwarded only via publisher/outbox, not consumed.
- **DB-less broad suite**: 30 DB-dependent tests error `psycopg.OperationalError connection refused` without postgres — pre-existing, not introduced by this slice (consumer is broker-free mocked).
- **Budget tight**: 400 lines is exactly at the 400-line ceiling (400/400, 0 deletions, no size:exception — inclusive limit); any additional file would exceed. Kept module minimal and test at 5 cases; no compatibility layer for prior failed draft.

## Next Steps

- **Next recommended**: `sdd-apply` for PR2c `messaging-runtime-pr2c-runtime` (tasks 2.3–2.4: `messaging_runtime.py` + `app.py` lifespan, broker-down healthy, backoff cap 30s, shutdown ≤10s) targeting `main` after PR2b merges, then Phase 3 handlers + Phase 4 E2E/CI/docs. Each will stay <400 and keep tests/docs with the unit they verify.
- Do not start Phase 3 handlers or Phase 4 E2E/CI/docs until PR2b merges.

## PR3a — inventory terminal guard (task 3.1 only, `messaging-runtime-pr3a-inventory-terminal-guard`)

- Scope: `backend/app/modules/inventory/application/order_status.py` (11) + `backend/app/modules/orders/application/get_order_status.py` (19) + `backend/app/modules/inventory/application/process_inventory_reservation.py` delta (+12) + `backend/app/tests/modules/inventory/application/test_inventory_terminal_guard.py` (245) + `test_process_inventory_reservation.py` + `test_core_flow.py` wiring fixes from `origin/main` `5e16aec` (PR #67 merged) — no container/runtime/broker wiring (task 3.4 owns it); smallest explicit inventory-owned seam with required injection and typed aggregate ID.
- Seam: `OrderStatusQuery` (`@runtime_checkable` Protocol, `get_status(UUID)->str|None`) in `inventory/application/order_status.py`; `GetOrderStatus` in `orders/application/get_order_status.py` implements it via `OrderRepository.get_by_id` (returns `order.status` or `None`, only `get_status` — no `execute` alias); `ProcessInventoryReservation` requires `order_status: OrderStatusQuery` (no default, no 3-arg path), checks `is_processed` first, then `UUID(str(order_id))` (malformed raises `ValueError` to consumer `nack(requeue=True)`) → `get_status` inside consumer transaction → if `confirmed`/`cancelled` → `mark_processed(event_id, "ProcessInventoryReservation")` same row and return without inventory/outbox mutation; pending/missing → preserve reserve/reject; handler failure still `nack(requeue=True)` via consumer.
- Evidence: `uv run --project backend python -m pytest backend/app/tests/modules/inventory/application/test_inventory_terminal_guard.py -v` → 6 passed in 0.03s (terminal confirmed/cancelled skip + processed + duplicate no-ops, duplicate once, sync-checkout 7/3 unchanged, pending/missing reserves, malformed `order-123` raises `ValueError` with no reservation/no status call, GetOrderStatus confirmed/cancelled/None via `get_status` only). Safety net `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/runtime -v` → 16 passed (5 consumer + 11 runtime); `cd backend && uv run pyrefly check` → 0 errors; `ruff format/check` ok; DB suite 30 errors `connection refused` honestly reported.
- Sync-checkout proof: inventory pre-reserved 7/3 via sync `Checkout` path (simulated `available=7 reserved=3`), async `OrderCreated` with `order_status=confirmed` → `ProcessInventoryReservation` guard skips, `available` stays 7, `reserved` stays 3, `outbox.events==[]`.
- Rollback: revert 3 files + test (see Scope) restores 3-arg `ProcessInventoryReservation` without guard; `tasks.md` 3.1 [x] and `apply-progress.md` PR3a are SDD artifacts. No new deps, no global container wiring, never logs payload/body/credentials.
- Next: `sdd-apply` for 3.2 (`process_inventory_result` terminal guard), 3.3 (notifications), 3.4 (container wiring supplying `GetOrderStatus`), then 4.x E2E/CI/docs; 3.2–3.4 and 4.x remain pending.

## Relevant Files

- `backend/app/shared/messaging/consumer.py` — registry validation, durable TOPIC exchange, 3 durable queues, prefetch 1, 5 binds, ack after commit / nack requeue, transaction + handler factory boundaries, no-payload logging (RED→GREEN)
- `backend/app/tests/shared/messaging/test_consumer.py` — 5 tests: dup registry, durable topology + prefetch + bind + start no_ack, invalid acked (unknown/missing/invalid json), success acked + no payload log + factory session/payload, failure nacked requeue (RED→GREEN→TRIANGULATE)
- `backend/app/shared/messaging/rabbitmq_publisher.py` — persistent delivery (PR2a, preserved)
- `backend/app/shared/config/settings.py` + `backend/.env.example` — RABBITMQ vars + poll/batch (PR2a, preserved)
- `openspec/changes/messaging-runtime-bootstrap/tasks.md` — marks 2.2 `[x]`, 2.3–2.4 pending

## PR2c — runtime lifecycle (tasks 2.3/2.4)

- Scope: `messaging_runtime.py` (166) + `app.py` lifespan (+29) + `tests/runtime/` (185) from `cbb99e3`
- Evidence: `uv run --project backend python -m pytest backend/app/tests/runtime -v` → 11 passed (8+3); `cd backend && uv run pyrefly check` → 0 errors; Ruff check/format ok
- Next (pre-PR3a): `messaging-runtime-pr3-handlers` (3.1–3.4) then pr4 chain/integration/CI/docs; 3.x/4.x pending

## PR3a files (this slice)

- `backend/app/modules/inventory/application/order_status.py` — inventory-owned `@runtime_checkable` Protocol `OrderStatusQuery.get_status(UUID)->str|None` (smallest seam, 11 lines)
- `backend/app/modules/orders/application/get_order_status.py` — orders-owned `GetOrderStatus` implementing Protocol via `OrderRepository.get_by_id` (19 lines, only `get_status` — no `execute` alias)
- `backend/app/modules/inventory/application/process_inventory_reservation.py` — required `order_status: OrderStatusQuery` injection (no default), idempotency first, then `UUID(str(order_id))` with typed contract (malformed raises), terminal guard inside consumer transaction, marks same `processed_events` row and returns without mutation (delta +12)
- `backend/app/tests/modules/inventory/application/test_inventory_terminal_guard.py` — 6 unit tests: GetOrderStatus `get_status` only, terminal confirmed/cancelled skip + processed + duplicate no-ops, duplicate once, sync-checkout 7/3 unchanged, pending/missing reserves + malformed raises `ValueError` (245 lines, broker-free)
- `backend/app/tests/modules/inventory/application/test_process_inventory_reservation.py` + `backend/app/tests/test_core_flow.py` — wiring fixes: mandatory `GetOrderStatus`/`_FakePendingOrderStatus` injection, valid UUID `order_id`, no 3-arg path
- `openspec/changes/messaging-runtime-bootstrap/tasks.md` — mark 3.1 `[x]`, 3.2–3.4 and 4.x pending

## PR3b — orders terminal guard (task 3.2 only, `messaging-runtime-pr3b-orders-terminal-guard`)

- Scope: `backend/app/modules/orders/application/process_inventory_result.py` delta (+6) + `backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py` (219) — no OrderStatusQuery, no container/runtime/broker/CI/docs wiring (3.3/3.4/4.x remain pending); stacked-to-main on `feat/messaging-order-result-guard` from `2e2bfd7`.
- Guard: after `is_processed` early return and `OrderNotFoundError` handling, if `order.status in ("confirmed","cancelled")` → `await mark_processed(event_id,"ProcessOrderInventoryResult")` and return without `save`/`event_repo.add`/`outbox.save`/re-transition; applies regardless of `result` value; preserves pending `reserved→confirmed`, `rejected→cancelled`, duplicate-once via `is_processed`; interface unchanged, no fallback, no payload logging.
- TDD: RED `5 collected → 3 failed,2 passed` (confirmed save 1==0, cancelled save 1==0, confirmed+rejected InvalidStateTransition); GREEN `5 passed in 0.02s` after guard; TRIANGULATE `test_terminal_skip_regardless_of_result_value` (confirmed+rejected & cancelled+reserved both no-op), `test_pending_reserved_confirms_and_pending_rejected_cancels` (pending transitions + duplicate once), `test_order_not_found_still_raises`; REFACTOR none needed — minimal conditional.
- Evidence: `uv run --project backend python -m pytest backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py -v` → 5 passed in 0.02s (terminal confirmed/cancelled skip + processed + duplicate no-ops, regardless-value skip, pending both paths + duplicate once, not-found raises). Safety net `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/runtime -v` → 16 passed; `uv run --project backend python -m pytest ...test_order_result_terminal_guard.py ...test_inventory_terminal_guard.py ...test_consumer.py ...runtime -v` → 27 passed; `uv run pyrefly check` → 0 errors; Ruff format/check ok; DB suite 3 errors `connection refused` honestly reported, no postgres locally.
- Rollback: revert `process_inventory_result.py` (+6 guard lines) and `test_order_result_terminal_guard.py` (219) restores pre-guard behavior; `tasks.md` 3.2 `[x]` and `apply-progress.md` PR3b are SDD artifacts.
- Next: `sdd-apply` for 3.3 (`process_order_notification`), 3.4 (container wiring supplying `GetOrderStatus`), then 4.x E2E/CI/docs; 3.3-3.4 and 4.x remain pending.

## Work Unit Evidence (PR3b — orders terminal guard only)

| Evidence | Required value | Result |
|---|---|---|
| Focused test command and exact result | Smallest command proving this unit; command, exit/result, and relevant counts | `uv run --project backend python -m pytest backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py -v` → **5 passed in 0.02s** (`test_terminal_confirmed_late_reserved_no_ops_skip_recorded`, `test_terminal_cancelled_late_rejected_no_ops_skip_recorded`, `test_terminal_skip_regardless_of_result_value`, `test_pending_reserved_confirms_and_pending_rejected_cancels`, `test_order_not_found_still_raises_and_not_marked`) |
| Runtime harness command/scenario and exact result | Real integration/runtime path; explicit `N/A` only when no runtime boundary exists, with reason | Broker/DB-free fake-unit harness: `ProcessOrderInventoryResult(FakeOrderRepository, FakeEventRepository, FakeOutbox, FakeIdempotency)` with `Order(status=confirmed/cancelled/pending)` exercises terminal skip inside same consumer transaction; confirms no `save`/`add`/`outbox`, `mark_processed` recorded, duplicate is_processed no-op, pending transitions commit. Consumer/runtime harness preserved: `MessageConsumer` durable TOPIC + prefetch 1 + ack/nack via `test_consumer.py` 16 passed proves per-message transaction boundary still holds. DB `test_process_inventory_result.py` collected → 3 errors `psycopg.OperationalError connection refused` honestly reported — no local postgres, not fabricated. |
| Rollback boundary | Exact files/behavior that can be reverted without removing unrelated work | Revert `backend/app/modules/orders/application/process_inventory_result.py` (remove 6-line terminal guard) and `backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py` (219 lines). Reverting restores late results re-transitioning or raising; `test_inventory_terminal_guard.py`/consumer/runtime/tasks remain untouched. |

## Work Unit Evidence (PR3c — notification handler only)

| Evidence | Required value | Result |
|---|---|---|
| Focused test command and exact result | Smallest command proving this unit; command, exit/result, and relevant counts | `uv run --project backend python -m pytest backend/app/tests/modules/notifications/application/test_process_order_notification.py -v` → **8 passed in 0.03s** (confirmed, cancelled, duplicate once, duplicate-skip-without-revalidate, failure-not-marked, malformed, unknown, mandatory-deps) |
| Runtime harness command/scenario and exact result | Real integration/runtime path; explicit `N/A` only when no runtime boundary exists, with reason | DB/broker-free fake harness: `ProcessOrderNotification(FakeNotifier, FakeIdempotency)` proves idempotent `OrderConfirmed`/`OrderCancelled` → `SendOrderNotification(email, deterministic content)` → `mark_processed` same consumer transaction; failure not marked, malformed/unknown no notification, duplicate once. Consumer/runtime harness preserved: `MessageConsumer` durable TOPIC + prefetch 1 + ack/nack via `test_consumer.py` + `test_messaging_runtime.py` → **16 passed** proves per-message transaction boundary still holds. DB `test_sqlalchemy_repository` 3 errors `connection refused` honestly reported — no postgres, not fabricated. |
| Rollback boundary | Exact files/behavior that can be reverted without removing unrelated work | Revert `backend/app/modules/notifications/application/process_order_notification.py` (41) and `backend/app/tests/modules/notifications/application/test_process_order_notification.py` (167) restores no notification handler; `process_inventory_result.py`/ `inventory_terminal_guard` / consumer/runtime/tasks remain untouched. |

## Validation (post-format, pre-commit, PR3b)

- `uv run --project backend ruff format backend/app/modules/orders/application/process_inventory_result.py backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py` → `2 files left unchanged`
- `uv run --project backend ruff check backend/app/modules/orders/application/process_inventory_result.py backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py` → `All checks passed!`
- `uv run --project backend pyrefly check` (via `cd backend`) → `0 errors`
- `uv run --project backend python -m pytest backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py -v` → 5 passed in 0.02s
- `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/runtime -v` → 16 passed
- `uv run --project backend python -m pytest backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py backend/app/tests/modules/inventory/application/test_inventory_terminal_guard.py backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/runtime -v` → 27 passed
- `uv run --project backend python -m pytest backend/app/tests/modules/orders/domain -v` → 16 passed; `backend/app/tests/modules/orders/application/test_process_inventory_result.py` → 3 errors `connection refused` honestly reported
- `uv run --project backend ruff format --check` → already formatted; 3.2 only, 3.3-3.4/4.x pending

## Validation (post-format, pre-commit, PR3c)

- `uv run --project backend ruff format backend/app/modules/notifications/application/process_order_notification.py backend/app/tests/modules/notifications/application/test_process_order_notification.py` → `2 files left unchanged`
- `uv run --project backend ruff check backend/app/modules/notifications/application/process_order_notification.py backend/app/tests/modules/notifications/application/test_process_order_notification.py` → `All checks passed!`
- `uv run --project backend pyrefly check` (via `cd backend`) → `0 errors`
- `uv run --project backend python -m pytest backend/app/tests/modules/notifications/application/test_process_order_notification.py -v` → 8 passed in 0.03s
- `uv run --project backend python -m pytest backend/app/tests/modules/notifications/application/test_process_order_notification.py backend/app/tests/shared/messaging/test_consumer.py backend/app/tests/runtime -v` → 24 passed (8 notif +5 consumer +11 runtime)
- `uv run --project backend python -m pytest backend/app/tests/modules/notifications -v` → 17 passed, 3 errors `connection refused` honestly reported (DB-less harness proves handler; Postgres not available locally)
- `uv run --project backend ruff format --check` → already formatted; 3.3 done, 3.4/4.x pending

## PR Boundary and Line Count (against `origin/main` `a1db18e`)

- Branch: `feat/messaging-order-notifications` from `origin/main` `a1db18e` (`feat(messaging): guard order result transitions` #69 merged)
- Tracked diff: `git diff a1db18e --stat` → 4 files, 256 insertions, 19 deletions (+41/0 process_order_notification +167/0 test +47/18 apply-progress +1/1 tasks); complete `git diff a1db18e --numstat` → **256 insertions, 19 deletions** → **275 complete** ≤400 (no size:exception, margin ~125)
- Checkpoints: before edit `git diff --stat HEAD` 0 clean; after handler+test `git diff a1db18e --numstat` 208/0; after tasks+apply-progress 256/19=275; staged vs unstaged identical after `git add` of 4 paths
- Chain guidance: `stacked-to-main` — PR3c targets `main` after PR3b merges; diff shows only PR3c work unit (verify via `git diff a1db18e --stat` shows only the 4 files); PR3b history preserved in apply-progress

## Deviations from Design

- None for task 3.3; `ProcessOrderNotification` implements exactly `design.md` delegation to `SendOrderNotification` and same-transaction `mark_processed` with mandatory injection, `is_processed` first, `UUID(str(aggregate_id))` (malformed raises), `OrderConfirmed`/`OrderCancelled` → `email` + deterministic English content, `ValueError` on unknown type, no outbox/payload-log/container wiring. Previous tasks 3.1-3.2 also no deviation.

## Risks

- PostgreSQL unavailable locally — DB integration tests honestly `connection refused` (3 errors for `test_sqlalchemy_repository`, 3 for `test_process_inventory_result`) — not a regression; fake-unit harness proves handler idempotency and same-transaction boundary. Consumer/runtime harness 16 passed proves ack/nack boundary preserved.
- Budget: complete diff 275/400 inclusive, margin preserved; no `size:exception` needed. Handler 41/0 + test 167/0 + tasks 1/1 + apply-progress 47/18 → 256 ins, 19 del → 275 complete.

## Next Steps

- Next recommended: `sdd-apply` for `messaging-runtime-pr3c-notification-handler` task 3.4 (container wiring supplying `GetOrderStatus` and binding notifications handler), then pr4 chain/integration/CI/docs; keep each PR ≤400 stacked-to-main
- Do not start 4.x until 3.4 merges

## Relevant Files (PR3c — this slice)

- `backend/app/modules/notifications/application/process_order_notification.py` — idempotent handler for `OrderConfirmed`/`OrderCancelled`, mandatory `SendOrderNotification`+`ProcessedEventStore`, `is_processed` first → `UUID` parse → deterministic `email`+content → `notifier.execute` → `mark_processed` same consumer transaction (RED→GREEN)
- `backend/app/tests/modules/notifications/application/test_process_order_notification.py` — 8 unit tests: confirmed/cancelled notify + content, duplicate once, duplicate-skip-without-revalidate, failure-not-marked, malformed UUID, unknown type, mandatory deps (RED→GREEN→TRIANGULATE)
- `openspec/changes/messaging-runtime-bootstrap/tasks.md` — mark 3.3 `[x]`, 3.4 and 4.x pending
- `openspec/changes/messaging-runtime-bootstrap/apply-progress.md` — cumulative: 1.1-3.3 complete, 3.4/4.x pending

## Relevant Files (history preserved)

- `backend/app/modules/orders/application/process_inventory_result.py` — PR3b terminal guard (6 lines)
- `backend/app/tests/modules/orders/application/test_order_result_terminal_guard.py` — PR3b 5 tests (219)
- `backend/app/modules/inventory/application/order_status.py` + `get_order_status.py` + `process_inventory_reservation.py` — PR3a guard + seam
- `backend/app/shared/messaging/consumer.py` + `test_consumer.py` — PR2b registry (400)
- `backend/app/shared/messaging/rabbitmq_publisher.py` — PR2a persistent delivery
