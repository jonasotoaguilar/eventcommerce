# Design: Messaging Runtime Bootstrap

## Technical Approach

Add a composition-root runtime in `backend/app/messaging_runtime.py`; keep AMQP mechanics in `backend/app/shared/messaging/`. FastAPI lifespan starts a retrying publisher, transactional outbox scheduler, and registry-driven consumers without making RabbitMQ an API-startup dependency. Each broker message gets one SQLAlchemy session/transaction, preserving `pending → confirmed/cancelled`; payments, DLQ, full `EventEnvelope`, and a separate worker remain non-goals.

## Architecture Decisions

| Area | Choice | Rejected | Rationale |
|---|---|---|---|
| Terminal guard | `ProcessInventoryReservation` depends on an inventory-owned `OrderStatusQuery` protocol; composition supplies new orders use case `GetOrderStatus`. `ProcessOrderInventoryResult` checks the order it already loads. Terminal skips call `mark_processed`. | Inventory importing orders repositories; shared global guard | Cross-context knowledge stays in the composition root; both checks share the message transaction. Inventory reservation reuses `lock_and_check_availability()` for ordered row locks. |
| Registry/topology | `ConsumerBinding(queue, event_types, consumer_name, handler_factory)` in `consumer.py`; `messaging_runtime.py` owns three concrete bindings. Factories receive the per-message `AsyncSession`; fresh module containers build handlers. | Global container overrides; module-specific loops | One ack policy, no concurrent mutable container/session sharing, and no shared→domain imports. |
| Retry/lifespan | Initial connect is non-fatal; a supervisor retries transient connection failures with full-jitter exponential delay capped at 30s. Robust connections recover declared topology. Shutdown stops intake, waits up to 10s, then closes so RabbitMQ requeues unfinished deliveries. | Fail-fast; unbounded shutdown | Meets API degradation and deterministic cleanup. FastAPI lifespan runs setup before and cleanup after `yield`; aio-pika robust channels restore topology. |
| Outbox claim | `OutboxWorker` owns an `async_sessionmaker`; `run_once` uses `Session.begin()`, `with_for_update(skip_locked=True)`, ordered capped rows, publish confirms, per-row failure logging/continue, mark-success, then commit. | Claim without transaction; `processing` schema | Concurrent workers hold disjoint claims. Crash-after-confirm remains at-least-once and is absorbed by consumer idempotency. |
| Wire boundary | Persistent JSON body; `message_id`, `event_type`, `aggregate_id` headers; routing key equals type. Consumer validates required metadata and object payload. Unknown/malformed messages are warning-logged and acked; payloads/credentials are never logged. | Full `EventEnvelope`; poison requeue | Matches the approved contract without correlation-schema expansion. |

Sources: locked aio-pika `10.0.1`, FastAPI `0.136.1`, SQLAlchemy `2.0.49`; official docs confirm robust topology recovery/publisher confirms, lifespan cleanup, one `AsyncSession` per task, and `with_for_update(skip_locked=True)`.

## Data Flow and Contracts

```text
DB outbox --claim/publish/commit--> order.events --> durable queue
                                                       |
message --> session + advisory idempotency lock --> handler --> commit --> ack
                                                       `-- error --> rollback --> nack(requeue=True)
```

Bindings: `inventory.order_created:{OrderCreated}`, `orders.inventory_result:{InventoryReserved,InventoryRejected}`, `notifications.order_terminal:{OrderConfirmed,OrderCancelled}`; all durable, prefetch `1`. Before handler execution, reuse `acquire_claim_lock(event_id, consumer_name)`; a concurrent duplicate waits, observes `processed_events`, commits no effects, then acks. `ProcessOrderNotification` delegates to `SendOrderNotification` and records processing in the same transaction. `OrderCreated` event-store and outbox payloads both serialize `customer_id` plus item dictionaries.

## File Changes

| Action | Files |
|---|---|
| Create | `backend/app/messaging_runtime.py`; `backend/app/shared/messaging/consumer.py`; `backend/app/modules/orders/application/get_order_status.py`; `backend/app/modules/inventory/application/order_status.py`; `backend/app/modules/notifications/application/process_order_notification.py`; `backend/alembic/versions/<revision>_index_pending_outbox.py`; runtime/handler/chain/broker integration tests under `backend/app/tests/` |
| Modify | `backend/app/app.py`, `shared/config/settings.py`, `shared/messaging/{idempotency,outbox_repository,outbox_worker,rabbitmq_publisher}.py`; orders/inventory/notifications containers and handlers; `create_order.py`; existing messaging/handler tests; `.github/workflows/api-ci.yml`, `backend/.env.example`; `ARCHITECTURE.md`, `docs/GLOSSARY.md`, `docs/adr/0002-use-choreography.md`, `README.md` |
| Delete | None |

Migration creates `ix_outbox_events_status_created_at` on `(status, created_at)` from head `8d9e0f1a2b3c`; downgrade drops it. `EXPLAIN` integration evidence must show an index plan with representative pending/published volume.

## Testing Strategy

| Layer | Coverage |
|---|---|
| Unit | Registry validation, persistent headers, retry/backoff via injected sleep/jitter, shutdown timeout, malformed/unknown ack, failure nack, notification and terminal skips. |
| PostgreSQL integration | Disjoint concurrent claims; advisory-lock duplicate; atomic handler/outbox/processed commit and rollback; index plan; inventory locking. |
| Chain/E2E | Broker-free fake publisher/messages complete order→inventory→terminal notification; default suite needs no broker. One `integration`-marked real RabbitMQ persistence/restart/topology test runs only when `EVENTCOMMERCE_RUN_RABBITMQ_INTEGRATION=1`; CI adds a healthy RabbitMQ service and enables it. |

Observability uses existing key=value logging at connect/retry, publish, dispatch, duplicate/terminal skip, ack/nack, and shutdown, carrying queue/type/event/aggregate IDs and durations. No new metrics/tracing claim.

## Threat Matrix

| Boundary | Applicability | Design response / RED tests |
|---|---|---|
| Documentation-like paths | N/A — no executable classification | None |
| Git repository selection | N/A — no Git commands | None |
| Commit state | N/A — no commit automation | None |
| Push state | N/A — no push automation | None |
| PR commands | N/A — no PR automation | None |

## Migration / Rollout

Apply the additive index before enabling lifespan wiring. Roll back runtime/CI/docs and downgrade the index together; pending rows stay pending and synchronous checkout remains operational. Logs prove broker degradation and backlog recovery.

## Open Questions / Contradiction

- [ ] **Spec contradiction:** `project-foundation-docs` labels `InventoryRejected`, `OrderConfirmed`, and `OrderCancelled` as “Target Events,” while `messaging-runtime` requires them live on implemented queues. Tasks must first correct that delta classification; implementation must not ship docs that call live runtime events Target.
- [ ] Delivery chain strategy remains intentionally unresolved until `sdd-tasks` forecasts the 800-line review budget.
