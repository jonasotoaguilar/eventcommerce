# ADR 0003: Use dependency-injector for DI

## Status

Accepted (MVP Target)

## Context

The published Git base lacks `dependency-injector` containers and per-request session scoping. Modules use plain FastAPI routers without DI wiring (`routes/v1/router.py`). DI containers are accepted for the MVP Target to provide consistent wiring patterns and testable provider overrides across all bounded contexts.

## Decision

Continue with `dependency-injector`: one container per bounded context, module-level global container, API router wiring, and per-request `session` override reset in `finally`.

## Options considered

| Option | Assessment |
|--------|------------|
| Manual constructor injection | Zero dependencies, but more boilerplate in routes and tests. |
| dependency-injector | Already used in orders; supports scoped overrides and fits the module layout. |
| Another DI framework | Would add migration cost without clear gain over the current library. |

## Consequences

- **Positive**: consistent wiring pattern across modules once implemented; request-scoped sessions keep units of work clean.
- **Negative**: containers must be created for all modules before the pattern is usable across contexts.
- **Neutral**: tests can override providers at the container boundary.

## References

- [ARCHITECTURE.md](../../ARCHITECTURE.md) — Cross-cutting concerns / DI container strategy
- `backend/app/modules/orders/api/container.py` (Target)
- `backend/app/modules/orders/api/routes.py` (Target)
- `backend/app/modules/inventory/api/container.py` (Target)
- `backend/app/modules/payments/api/container.py` (Target)
- `backend/app/modules/notifications/api/container.py` (Target)
