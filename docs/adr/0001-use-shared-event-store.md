# ADR 0001: Use a shared event store

## Status

Accepted (MVP Target)

## Context

The published Git base currently lacks a shared event store; bounded contexts use local persistence without a unified domain-events table. A single event store is needed so `orders`, `inventory`, `payments`, and `notifications` produce domain events through a common stream for order timeline audit.

## Decision

Accept a shared event store for the MVP Target: a neutral `DomainEvent` base, a single `domain_events` table, and `SqlAlchemyEventRepository`. Each context stores its own events through the shared repository. The implementation lives under the planned path `backend/app/shared/events/`.

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
- `backend/app/shared/events/event_repository.py` (Target)
- `backend/app/shared/events/models.py` (Target)
- `backend/alembic/versions/` — planned migration path (Target)
