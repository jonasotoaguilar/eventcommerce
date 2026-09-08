# ADR 0002: Use event choreography

## Status

Delivered

## Delivery scope (honest boundary)

Delivered: outbox scheduler + RabbitMQ publisher + AMQP consumer wired into the app lifespan with three durable queues and idempotent handlers; broker-free chain proof (`backend/app/tests/runtime/test_chain_e2e.py`) and gated real-broker proof in CI (`backend/app/tests/integration/test_rabbitmq_integration.py` + rabbitmq service in `.github/workflows/api-ci.yml`). Live broker delivery requires RabbitMQ. Not claimed: production deployment, operations/runbooks, observability, saga orchestration, dead-letter handling, or the five-state lifecycle.

## Context

The messaging primitives this decision depends on exist and are now wired: the shared event envelope, the transactional outbox (`outbox_events` + `SqlAlchemyOutboxRepository` + `9e0f1a2b3c4d` index), and the idempotency store (`processed_events` + `ProcessedEventStore`) are implemented and exercised by both the synchronous checkout path and the wired choreography runtime. `backend/app/messaging_runtime.py` builds the outbox scheduler, RabbitMQ publisher, and AMQP consumer (durable `order.events` TOPIC exchange, three queues, prefetch 1); `backend/app/app.py` starts/stops the runtime in its lifespan (broker-down startup stays healthy, shutdown closes within 10s). Idempotent handlers (`ProcessInventoryReservation`, `ProcessOrderInventoryResult`, `ProcessOrderNotification`) react to published events, each committing handler + `processed_events` in one per-message transaction.

## Decision

Use event choreography for the MVP: contexts react to events published via the transactional outbox. `OrderCreated` triggers inventory reservation, `InventoryReserved` triggers payment authorization and order confirmation, `InventoryRejected` triggers cancellation, and order terminal events trigger notifications.

## Options considered

| Option | Assessment |
|--------|------------|
| Choreography + outbox | Matches existing primitives; loose coupling; no single point of failure. |
| Orchestrated saga | Easier compensation visibility, but adds a coordinator before the basic flow is wired. |

## Consequences

- **Positive**: aligns with the implemented outbox and envelope; lets each context evolve independently.
- **Negative**: distributed compensations (e.g., release inventory on payment failure) are harder to trace than a saga log.
- **Neutral**: future evolution to an orchestrated saga or hybrid is not precluded.

## References

- [PRD.md](../../PRD.md) — MVP Target / coordination model
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — Patterns
- [GLOSSARY.md](../GLOSSARY.md) — choreography, transactional outbox, idempotency
- `backend/app/shared/messaging/outbox_repository.py` — implemented outbox repository
- `backend/app/shared/messaging/idempotency.py` — implemented idempotency store
- `backend/app/shared/messaging/rabbitmq_publisher.py` — connected by the runtime (persistent delivery, headers, no payload logging)
- `backend/app/shared/messaging/outbox_worker.py` — driven by the runtime scheduler loop
- `backend/app/shared/messaging/consumer.py` — three-queue registry wired by `backend/app/messaging_runtime.py`
- `backend/app/messaging_runtime.py` + `backend/app/app.py` lifespan — runtime wiring
- `backend/app/tests/runtime/test_chain_e2e.py` — broker-free chain proof
- `backend/app/tests/integration/test_rabbitmq_integration.py` + `.github/workflows/api-ci.yml` — gated real-broker proof in CI
