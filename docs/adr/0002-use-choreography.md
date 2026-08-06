# ADR 0002: Use event choreography

## Status

Partially implemented

## Context

The messaging primitives this decision depends on now exist: the shared event envelope, the transactional outbox (`outbox_events` + `SqlAlchemyOutboxRepository`), and the idempotency store (`processed_events` + `ProcessedEventStore`) are implemented and exercised by the synchronous checkout path. The full choreography wiring is not delivered: there is no outbox worker/scheduler lifespan integration, no RabbitMQ publisher connection, and no AMQP consumer, so no context reacts to a published event. The current checkout is a deliberate synchronous commerce path.

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
- `backend/app/shared/messaging/rabbitmq_publisher.py` — publisher module exists; not wired
- `backend/app/shared/messaging/outbox_worker.py` — worker module exists; no scheduler/lifespan integration
