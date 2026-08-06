# ADR 0001: Use a shared event store

## Status

Accepted (current implementation)

## Context

Bounded contexts need a unified domain-events stream for order timeline audit. A shared event store is implemented so `orders` (and, via checkout, the synchronous commerce path) produces domain events through a common stream: a neutral `DomainEvent` base, a single `domain_events` table, and `SqlAlchemyEventRepository` at `backend/app/shared/events/`. The orders HTTP API reads timelines from it (`GET /api/v1/orders/{order_id}/timeline`).

## Decision

Accept a shared event store for the MVP: a neutral `DomainEvent` base, a single `domain_events` table, and `SqlAlchemyEventRepository`. Each context stores its own events through the shared repository. The implementation lives under `backend/app/shared/events/`.

## Options considered

| Option | Assessment |
|--------|------------|
| Per-module event tables | Clean ownership per bounded context, but duplicated schema and a harder cross-context timeline. |
| Shared event store | Simpler audit stream, one migration path, but shared persistence infrastructure. |

## Consequences

- **Positive**: a consistent timeline, one event repository, and less schema duplication.
- **Negative**: schema changes to `domain_events` affect all contexts; ownership of the shared table is a coordination concern.
- **Neutral**: requires clear event-type governance via `docs/GLOSSARY.md`.

## References

- [ARCHITECTURE.md](../../ARCHITECTURE.md) — Patterns / Current Implementation Status matrix
- [GLOSSARY.md](../GLOSSARY.md) — event vocabulary
- `backend/app/shared/events/domain.py` — `DomainEvent` base
- `backend/app/shared/events/models.py` — `domain_events` ORM model
- `backend/app/shared/events/repository.py` — event store protocol and `TimelineEvent` read model
- `backend/app/shared/events/event_repository.py` — `SqlAlchemyEventRepository`
- `backend/alembic/versions/9b69790738e5_replace_order_events_with_shared_domain_events.py` — migration introducing the shared table
