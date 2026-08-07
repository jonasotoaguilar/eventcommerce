# messaging-runtime Specification

## Purpose

Durable outbox forwarding, lifecycle-managed AMQP dispatch, idempotent choreography handlers, and runtime verification of the order chain alongside synchronous checkout.

## Non-Goals

Five-state lifecycle (async path keeps `pending → confirmed/cancelled`); saga orchestration, DLQ/retry exhaustion, wire envelope correlation, separate worker process; `checkout-end-to-end` changes.

## Requirements

### Requirement: OrderCreated Payload Completeness

`OrderCreated` rows MUST include `customer_id` and `items` (`product_id`, `quantity`) so reservation runs from the message alone.

#### Scenario: Reservable items on order-created row

- GIVEN an order created via `POST /api/v1/orders`
- WHEN its `OrderCreated` row is read
- THEN payload has `customer_id` and `items` matching the request

#### Scenario: Checkout-created row carries items

- GIVEN an order created via synchronous checkout
- WHEN its `OrderCreated` row is read
- THEN payload has the same reservable `items` as the request

### Requirement: Durable Outbox Claiming and Indexing

`get_pending` MUST claim with `FOR UPDATE SKIP LOCKED`, ordered by `created_at`, batch-capped; a migration MUST index `outbox_events(status, created_at)`.

#### Scenario: Concurrent workers claim disjoint rows

- GIVEN two workers poll the same pending rows
- WHEN both claim
- THEN each row claimed once, no double publish

#### Scenario: Polling uses the composite index

- GIVEN migration applied
- WHEN the pending-query plan is explained
- THEN it uses the `(status, created_at)` index, not a scan

### Requirement: Persistent Forwarding

Publisher MUST send `delivery_mode=PERSISTENT`, `message_id=event.id`, headers `event_type`/`aggregate_id`, JSON payload; rows mark `published` only after successful publish.

#### Scenario: Message survives broker restart

- GIVEN a persistent message published
- WHEN broker restarts before consumption
- THEN message redelivered from the durable queue

#### Scenario: Publish failure leaves row pending

- GIVEN broker unreachable during `run_once`
- WHEN publish raises
- THEN row stays `pending`, error logged, worker continues

### Requirement: Lifespan Bootstrap, Retry, Graceful Shutdown

Lifespan MUST start publisher connect, settings-driven outbox scheduler, and consumer runtime. Broker connect failure MUST NOT fail startup; background retry logs attempts. Shutdown MUST cancel scheduler and close connections.

#### Scenario: API healthy with broker down

- GIVEN RabbitMQ down at startup
- WHEN app starts
- THEN `/health` serves and retry loop logs

#### Scenario: Scheduler forwards pending rows

- GIVEN pending rows and configured poll interval
- WHEN interval elapses
- THEN `run_once` runs with configured batch size

#### Scenario: Graceful shutdown

- GIVEN shutdown signal
- WHEN lifespan exits
- THEN scheduler cancelled, connections closed, no in-flight message left unacked past timeout

### Requirement: Consumer Registry and Queue Bindings

Shared consumer MUST declare durable queues `inventory.order_created`, `orders.inventory_result`, `notifications.order_terminal` on `order.events`, prefetch=1, dispatching by `event_type` (`OrderCreated`→inventory; `InventoryReserved`/`InventoryRejected`→orders; `OrderConfirmed`/`OrderCancelled`→notifications). Unregistered types MUST be acked and logged.

#### Scenario: Durable queues with prefetch 1

- GIVEN runtime startup
- WHEN queues bind
- THEN all three durable, prefetch=1, bound per mapping

#### Scenario: Unknown type cannot poison

- GIVEN unregistered `event_type`
- WHEN consumed
- THEN acked with warning, never requeued

### Requirement: Per-Message Transaction, Ack, Nack

Handle + `processed_events` row MUST commit in ONE transaction; ack after commit, `nack(requeue=True)` after rollback.

#### Scenario: Success acks after commit

- GIVEN valid message
- WHEN handler succeeds
- THEN processed row and outbox emissions commit, then ack

#### Scenario: Handler failure requeues

- GIVEN handler raises
- WHEN processing fails
- THEN rollback, no processed row, nack with requeue

#### Scenario: Duplicate delivery no-ops

- GIVEN same `message_id` redelivered
- WHEN handled again
- THEN processed row detected, no repeat side effect, ack

### Requirement: Idempotent Handlers and Terminal Guards

Inventory and order-result handlers MUST skip terminal (`confirmed`/`cancelled`) orders, recording the skip as processed; late/duplicate events MUST NOT re-reserve, re-transition, or poison.

#### Scenario: Late result on confirmed order

- GIVEN order `confirmed`
- WHEN late `InventoryRejected` consumed
- THEN no-op, skip recorded, ack, order stays `confirmed`

#### Scenario: Sync checkout not double-reserved

- GIVEN checkout-created order (inventory already reserved)
- WHEN its `OrderCreated` consumed
- THEN guard skips reservation, count unchanged

#### Scenario: Duplicate OrderCreated reserves once

- GIVEN same `OrderCreated` delivered twice, order non-terminal
- WHEN both handled
- THEN reserved once, transitioned once

### Requirement: Notification Consumer Handler

Notifications MUST provide an idempotent handler for `OrderConfirmed`/`OrderCancelled` delegating to `SendOrderNotification`, recording the processed row in the same transaction.

#### Scenario: Terminal event notifies

- GIVEN `OrderConfirmed` message
- WHEN handler runs
- THEN `SendOrderNotification` executes, processed row commits

#### Scenario: Duplicate notifies once

- GIVEN same terminal event redelivered
- WHEN handled twice
- THEN notification sent once

### Requirement: Broker-Free Tests and Gated Integration

Runtime MUST be covered broker-free (mocked `aio_pika`/fake messages), incl. a chain e2e to terminal notification; ONE gated RabbitMQ integration test MUST run in CI via a rabbitmq service, skipping when unreachable; `.env.example` MUST list `EVENTCOMMERCE_RABBITMQ_*`.

#### Scenario: Local suite green without broker

- GIVEN no RabbitMQ
- WHEN `pytest` runs
- THEN broker-free tests pass, gated test skipped

#### Scenario: CI exercises real broker

- GIVEN rabbitmq service in CI
- WHEN workflow runs
- THEN gated test executes end-to-end

#### Scenario: Env example covers broker

- GIVEN `.env.example` read
- WHEN broker vars checked
- THEN `HOST/PORT/USER/PASSWORD/VHOST` present
