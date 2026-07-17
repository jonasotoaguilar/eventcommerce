# Architecture Decision Records

Significant architecture and product decisions for EventCommerce. Each record is a decision, not a log entry.

## Status rules

| Status | Meaning |
|--------|---------|
| **Accepted (current implementation)** | The decision is implemented and live in the working tree. |
| **Partially implemented** | The pattern is accepted and proven in at least one place, but not replicated everywhere. |
| **Accepted (MVP Target)** | The decision is approved for the MVP vertical slice but has no implementation yet. |
| **Deprecated / Superseded** | Replaced by a newer ADR; not used for this foundation set. |

The status column is **independent of the horizon tags** in `PRD.md` and `ARCHITECTURE.md`. `Now` / `MVP Target` / `Future` describe planning buckets; the ADR status describes the implementation state of that decision.

## Index

| # | Title | Status |
|---|-------|--------|
| 0001 | [Use a shared event store](./0001-use-shared-event-store.md) | Accepted (MVP Target) |
| 0002 | [Use event choreography](./0002-use-choreography.md) | Accepted (MVP Target) |
| 0003 | [Use dependency-injector for DI](./0003-use-dependency-injector.md) | Accepted (MVP Target) |
| 0004 | [Own IAM as a bounded context](./0004-own-iam-context.md) | Accepted (MVP Target) |
| 0005 | [Use deterministic simulated payments](./0005-use-deterministic-simulated-payments.md) | Accepted (MVP Target) |

## Interpretation

- **Now** — code exists and is wired enough to be exercised.
- **MVP Target** — approved for the next vertical slice, no code yet.
- **Future** — not committed; may be revisited.

See [ARCHITECTURE.md](../../ARCHITECTURE.md) for the current implementation matrix and [PRD.md](../../PRD.md) for product scope.
