# Apply Progress: Messaging Runtime Bootstrap

## Work Unit

- Change: `messaging-runtime-bootstrap`
- Work unit: `messaging-runtime-pr2a-publisher-settings` (tasks 2.1 + 2.5)
- Scope: PR2a only, tasks 2.1 and 2.5 stacked-to-main on branch `feat/messaging-runtime-pr2a-publisher-settings` based on PR1 commit `b24033207f242238ee0a737410b606a1ced65517`
- Artifact store: OpenSpec
- Mode: Strict TDD (`uv run --project backend python -m pytest`)
- Delivery: auto-chain, stacked-to-main; PR2a targets `main` after PR1 merges (PR2b will start from then-current `main` and also target `main`, not branch-to-branch)
- Review budget: 400 authored changed lines; current delta **58 lines** (see PR Boundary) — **within budget**
- Previous apply-progress: Engram #5248 `sdd/messaging-runtime-bootstrap/apply-progress` (PR1 tasks 1.1–1.5)
- Narrowing note: First run produced a 630-line full-PR2 candidate (tasks 2.1–2.5, 94 tracked + 536 new: `consumer.py` 144, `messaging_runtime.py` 115, `test_consumer.py` 174, `test_messaging_runtime.py` 103) which exceeded the 400 limit and returned `blocked`. Per corrective retry, that candidate’s 2.2–2.4 working-tree changes were **removed before the successful boundary**: restored `backend/app/app.py` to `b240332`, deleted `backend/app/shared/messaging/consumer.py`, `backend/app/messaging_runtime.py`, `backend/app/tests/shared/messaging/test_consumer.py`, `backend/app/tests/runtime/test_messaging_runtime.py` (and now-empty `backend/app/tests/runtime/`), and renamed the dedicated branch from `feat/messaging-runtime-pr2-runtime-bootstrap` to `feat/messaging-runtime-pr2a-publisher-settings`. PR1 files and behavior were preserved; no broad `git clean`/`reset` was used.

## Completed Tasks

- [x] 1.1 Correct `specs/project-foundation-docs/spec.md`: `InventoryRejected`/`OrderConfirmed`/`OrderCancelled` → Current Events (delivered-evidence); no AMQP-live claim pre-ship.
- [x] 1.2 RED→GREEN `create_order.py` + test: `OrderCreated` row carries `customer_id` + `items` (API + checkout).
- [x] 1.3 Migration `alembic/versions/<rev>_index_pending_outbox.py` (head `8d9e0f1a2b3c`): additive `(status, created_at)` index; downgrade drops.
- [x] 1.4 RED→GREEN `outbox_repository.py` + test: `get_pending` claims `FOR UPDATE SKIP LOCKED`, ordered, capped; disjoint workers.
- [x] 1.5 RED→GREEN `outbox_worker.py` + test: publish failure leaves row pending + logs + continues; publish only after confirm.
- [x] 2.1 RED→GREEN `rabbitmq_publisher.py` + test: PERSISTENT, `message_id`, `event_type`/`aggregate_id` headers; never log payloads.
- [ ] 2.2 RED→GREEN `shared/messaging/consumer.py` + test: registry validation; durable, prefetch 1; unknown/malformed acked; failure nack requeue.
- [ ] 2.3 RED→GREEN `messaging_runtime.py` + `backend/app/tests/runtime/`: broker-down startup healthy, backoff (cap 30s); shutdown cancels scheduler, closes ≤10s.
- [ ] 2.4 GREEN `app.py` lifespan: non-fatal connect; start/stop runtime ordering.
- [x] 2.5 GREEN `settings.py` + `.env.example`: `EVENTCOMMERCE_RABBITMQ_*` vars, poll interval, batch size.

## PR2a Implementation Summary

- 2.1 `rabbitmq_publisher.py`: Set `delivery_mode=DeliveryMode.PERSISTENT` (import `DeliveryMode`), `message_id=str(event.id)`, headers `event_type`/`aggregate_id`, `body=json.dumps(payload).encode()`, `content_type="application/json"`, `await exchange.publish(message, routing_key=event_type)`, then `logger.info("rabbitmq_publish event_id=%s event_type=%s aggregate_id=%s", ...)` without ever logging `payload`. `close()` unchanged. See `backend/app/shared/messaging/rabbitmq_publisher.py` 2.5–2.6 `DeliveryMode` import and lines 29–38 publish.
- 2.5 `settings.py` + `.env.example`: Added `rabbitmq_outbox_poll_interval: float = Field(default=1.0, alias="EVENTCOMMERCE_RABBITMQ_OUTBOX_POLL_INTERVAL")` and `rabbitmq_outbox_batch_size: int = Field(default=100, alias="EVENTCOMMERCE_RABBITMQ_OUTBOX_BATCH_SIZE")` to `Settings`; `.env.example` now lists `EVENTCOMMERCE_RABBITMQ_HOST/PORT/USER/PASSWORD/VHOST` (`localhost/5672/guest/guest//`) plus `OUTBOX_POLL_INTERVAL=1.0` and `OUTBOX_BATCH_SIZE=100`. No new dependency; `pydantic-settings` 2.14.2 `Field(alias=...)` verified.

## TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|---|
| 1.1 | `openspec/changes/messaging-runtime-bootstrap/specs/project-foundation-docs/spec.md` | Documentation | N/A — no executable surface | N/A — classification correction | Applied delta correction; no AMQP-live claim | N/A — non-executable | N/A |
| 1.2 | `app/tests/modules/orders/application/test_create_order.py`, `app/tests/modules/checkout/application/test_checkout.py` | PostgreSQL integration | `uv run --project backend python -m pytest ...test_create_order.py ...test_checkout.py` → 14 passed in 0.85s | Same command → 2 payload assertions failed because `items` absent | → 14 passed in 0.81s | Added multi-item case → 15 passed in 0.86s | No refactor needed |
| 1.3 | `app/tests/shared/messaging/test_pending_outbox_migration.py` | PostgreSQL integration | N/A — new migration/test | Test first → 1 failed `FileNotFoundError` for not-yet-created revision | → 1 passed in 0.15s | Added revision-chain metadata case → 2 passed | Migration minimal symmetric |
| 1.4 | `app/tests/shared/messaging/test_outbox_claiming.py` | PostgreSQL integration | `uv run --project backend python -m pytest app/tests/shared/messaging/test_outbox_repository.py` → 2 passed | New claim tests → 1 failed, 1 passed; concurrent workers overlapped | → 2 passed after `with_for_update(skip_locked=True)` | Ordered/capped + two-session disjoint claim both pass | No refactor needed |
| 1.5 | `app/tests/shared/messaging/test_outbox_worker.py` | PostgreSQL integration | Existing worker tests → 2 passed | New session-factory contract → 3 failed `AttributeError` | → 3 passed; failure row stayed pending, success published, log captured | Success/empty/failure-continue cases covered | Transaction ownership clean |
| 2.1 | `backend/app/tests/shared/messaging/test_rabbitmq_publisher.py` | Unit | `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_rabbitmq_publisher.py` → 3 passed in 0.05s (safety net) | Added `test_publish_persistent_headers_no_payload_log` → **2 failed** `AssertionError: assert <DeliveryMode.NOT_PERSISTENT: 1> == <DeliveryMode.PERSISTENT: 2>` in 0.07s (see first-run log) — proves test was written before fix | Fixed `rabbitmq_publisher.py` to set `DeliveryMode.PERSISTENT` + `logger.info` without payload → **4 passed in 0.05s** (3 existing + 1 new) | Same combined test also checks `message_id`/`aggregate_id` headers and `assert "cus_secret_123" not in caplog.text` with `caplog.at_level(logging.INFO, logger="app.shared.messaging.rabbitmq_publisher")` → 4 passed (triangulation: persistent + headers + payload-not-logged) | Merged two provisional tests into one combined assertion to stay under budget; no behavior refactor needed |
| 2.5 | `backend/app/shared/config/settings.py` + `backend/.env.example` | Unit | `uv run --project backend python -m pytest backend/app/tests/shared/config/test_settings.py` → 4 passed in 0.01s | N/A — GREEN per tasks.md | Added `Field(alias="EVENTCOMMERCE_RABBITMQ_OUTBOX_POLL_INTERVAL")` / `EVENTCOMMERCE_RABBITMQ_OUTBOX_BATCH_SIZE` and verified via `Settings()` env override (`EVENTCOMMERCE_RABBITMQ_OUTBOX_POLL_INTERVAL=2.5`, `BATCH_SIZE=50` → `2.5`/`50`) and defaults `1.0`/`100` → 4 passed + manual `Settings()` check | N/A — single field defaults, no branching | N/A |

## Work Unit Evidence (PR2a — publisher + settings only)

| Evidence | Required value | Result |
|---|---|---|
| Focused test command and exact result | Smallest command proving this unit; command, exit/result, and relevant counts | `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_rabbitmq_publisher.py backend/app/tests/shared/config/test_settings.py -v` → **8 passed in 0.04s** (4 publisher: `test_connect_declares_exchange`, `test_publish_sends_message`, `test_publish_without_connect_raises`, `test_publish_persistent_headers_no_payload_log`; 4 settings: `test_database_url_built_from_atomic_vars`, `test_rabbitmq_url_built_from_atomic_vars`, `test_test_database_url_builds_from_atomic_vars`, `test_app_vars_use_eventcommerce_prefix`). Extended focused `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_rabbitmq_publisher.py -v` → 4 passed in 0.05s |
| Runtime harness command/scenario and exact result | Real aio-pika message construction/publish mock verifying persistence, headers, message ID, configuration parsing, and payload not logged. Do not claim consumer/lifespan evidence for this slice. | `aio-pika` unit harness (no broker): `RabbitMQPublisher("amqp://guest:guest@localhost/").connect()` mocked via `patch("app.shared.messaging.rabbitmq_publisher.aio_pika.connect_robust")` declares durable `order.events` TOPIC; `publish(event)` constructs `aio_pika.Message(body=json.dumps(payload).encode(), content_type="application/json", delivery_mode=DeliveryMode.PERSISTENT, message_id=str(event.id), headers={"event_type": event.event_type, "aggregate_id": event.aggregate_id})` and calls `await exchange.publish(message, routing_key=event.event_type)`. Verified delivery_mode `PERSISTENT` (2) vs default `NOT_PERSISTENT` (1), `message_id` string, headers, `routing_key`, and that `caplog.text` never contains payload secret `cus_secret_123`. Settings harness: `Settings()` parses `EVENTCOMMERCE_RABBITMQ_OUTBOX_POLL_INTERVAL`/`BATCH_SIZE` via `Field(alias=...)`, computed `rabbitmq_url` `amqp://ru:rp@rh:5673/vhost`, and `.env.example` lists all five `HOST/PORT/USER/PASSWORD/VHOST` plus poll/batch. No consumer, lifespan, or scheduler was exercised for this slice. |
| Rollback boundary | Exact files/behavior that can be reverted without removing unrelated work | Revert `backend/app/shared/messaging/rabbitmq_publisher.py` (remove `DeliveryMode` import, `delivery_mode=DeliveryMode.PERSISTENT`, and `logger.info` without payload) and `backend/app/tests/shared/messaging/test_rabbitmq_publisher.py` (remove `test_publish_persistent_headers_no_payload_log` 33 lines), plus `backend/app/shared/config/settings.py` (remove two `Field` poll/batch) and `backend/.env.example` (remove 7 lines `RABBITMQ_HOST/PORT/USER/PASSWORD/VHOST/POLL_INTERVAL/BATCH_SIZE`). Reverting these restores the transient-delivery bug and the old `.env.example` that omitted broker vars; `outbox_repository.py`/`outbox_worker.py`/migration `9e0f1a2b3c4d`, consumer/runtime/app/handlers/CI/docs remain untouched. |

## Validation (post-format, pre-commit, after narrowing)

- `uv run --project backend ruff format backend/app/shared/messaging/rabbitmq_publisher.py backend/app/shared/config/settings.py backend/.env.example backend/app/tests/shared/messaging/test_rabbitmq_publisher.py` → formatters applied (if needed) before check-only
- `uv run --project backend ruff check backend/app/shared/messaging/rabbitmq_publisher.py backend/app/shared/config/settings.py` → All checks passed!
- `uv run --project backend ruff format --check backend/app/shared/messaging/rabbitmq_publisher.py backend/app/shared/config/settings.py backend/.env.example` → 3 files already formatted (formatted run before)
- `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_rabbitmq_publisher.py backend/app/tests/shared/config/test_settings.py -v` → 8 passed in 0.04s
- `uv run --project backend python -m pytest backend/app/tests/shared/messaging/test_rabbitmq_publisher.py -v` → 4 passed in 0.05s
- `uv run --project backend python -c "from app.shared.config.settings import Settings; s=Settings(); print(s.rabbitmq_outbox_poll_interval, s.rabbitmq_outbox_batch_size)"` → `1.0 100`; with env `2.5`/`50` → `2.5 50`
- Broad suite `uv run --project backend python -m pytest` on PR1 commit → 257 passed, 1 warning; on current narrowed branch without DB, `test_core_flow` errors `connection refused` — pre-existing, not a regression from this slice (no DB migration added).

## PR Boundary and Line Count (against PR1 commit `b24033207f242238ee0a737410b606a1ced65517`)

- Branch: `feat/messaging-runtime-pr2a-publisher-settings` (renamed from `feat/messaging-runtime-pr2-runtime-bootstrap` via `git branch -m feat/messaging-runtime-pr2-runtime-bootstrap feat/messaging-runtime-pr2a-publisher-settings`; never touched `main`/`master`; based on `b240332`, 1 commit ahead of `origin/feat/messaging-runtime-bootstrap`)
- Diff base: `b24033207f242238ee0a737410b606a1ced65517`
- Tracked diff: `git diff b240332 --stat` → **4 files, 58 insertions** (no deletions):
  - `7	0	backend/.env.example`
  - `7	0	backend/app/shared/config/settings.py`
  - `11	0	backend/app/shared/messaging/rabbitmq_publisher.py`
  - `33	0	backend/app/tests/shared/messaging/test_rabbitmq_publisher.py`
- `git diff b240332 --shortstat` → `4 files changed, 58 insertions(+)`
- Untracked SDD artifact (excluded from 400 budget): `openspec/changes/messaging-runtime-bootstrap/apply-progress.md` 104 lines, `tasks.md` delta 2 lines (marking 2.1/2.5)
- Total authored code delta **58 < 400** — within budget; no `size:exception` needed.
- Chain guidance: `stacked-to-main` — PR2a targets `main` after PR1 merges; later PR2b (`consumer`) will start from the then-current `main` and also target `main` (not branch-to-branch); this slice’s branch is independently reviewable and its diff shows only the publisher/settings slice (verified via `git diff b240332 --stat` showing only the 4 files).

## Deviations from Design

- None for this slice; `rabbitmq_publisher.py` now correctly sets `delivery_mode=DeliveryMode.PERSISTENT` per spec, and `settings.py`/`env.example` expose the specified `EVENTCOMMERCE_RABBITMQ_*` vars plus poll interval/batch size. Consumer/runtime/handlers intentionally deferred to later slices per the narrowed objective.

## Risks

- **Narrowed scope**: Tasks 2.2–2.4 remain pending and must not be claimed complete; `OrderCreated` rows will be forwarded by the (still-non-lifespan) publisher only when manually invoked, and no consumer is yet wired — expected until PR2b/PR2c per `stacked-to-main`.
- **DB-less broad suite**: `test_core_flow` fails without postgres (connection refused) — pre-existing, not introduced by this slice.

## Next Steps

- **Next recommended**: `sdd-apply` for PR2b `messaging-runtime-pr2b-consumer` (task 2.2: `consumer.py` + `test_consumer.py`, durable queues, prefetch 1, ack/nack) targeting `main` after this PR2a merges, then PR2c `messaging-runtime-pr2c-runtime` (tasks 2.3–2.4: `messaging_runtime.py` + `app.py` lifespan) also targeting `main`. Each will stay <400 and keep tests/docs with the unit they verify.
- Do not start Phase 3 handlers or Phase 4 E2E/CI/docs until PR2b/c are complete.

## Relevant Files

- `backend/app/shared/messaging/rabbitmq_publisher.py` — persistent delivery, headers, no payload log
- `backend/app/tests/shared/messaging/test_rabbitmq_publisher.py` — persistent/header/payload-not-logged test (RED→GREEN)
- `backend/app/shared/config/settings.py` — poll interval/batch size env vars
- `backend/.env.example` — all `EVENTCOMMERCE_RABBITMQ_*` plus poll/batch
- `openspec/changes/messaging-runtime-bootstrap/tasks.md` — marks 2.1/2.5 `[x]`, 2.2–2.4 pending
