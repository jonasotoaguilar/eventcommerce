# ADR 0002: Use event choreography

## Status

Accepted (MVP Target)

## Context

The published Git base currently lacks transactional outbox, idempotency, and RabbitMQ messaging primitives. The MVP choreography wiring requires all four bounded contexts (`orders`, `inventory`, `payments`, `notifications`) to react to domain events without a central orchestrator.

## Decision

Use event choreography for the MVP: contexts react to events published via the transactional outbox. `OrderCreated` triggers inventory reservation, `InventoryReserved` triggers payment authorization and order confirmation, `InventoryRejected` triggers cancellation, and order terminal events trigger notifications.

## Options considered

| Option | Assessment |
|--------|------------|
| Choreography + outbox | Matches existing primitives; loose coupling; no single point of failure. |
| Orchestrated saga | Easier compensation visibility, but adds a coordinator before the basic flow is wired. |

## Consequences

- **Positive**: aligns with the planned outbox and envelope; lets each context evolve independently.
- **Negative**: distributed compensations (e.g., release inventory on payment failure) are harder to trace than a saga log.
- **Neutral**: future evolution to an orchestrated saga or hybrid is not precluded.

## References

- [PRD.md](../../PRD.md) — MVP Target / coordination model
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — Patterns
- [GLOSSARY.md](../GLOSSARY.md) — choreography, transactional outbox, idempotency
- `backend/app/shared/messaging/outbox_repository.py` (Target)
- `backend/app/shared/messaging/idempotency.py` (Target)
