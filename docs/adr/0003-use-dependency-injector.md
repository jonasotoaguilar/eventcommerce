# ADR 0003: Use dependency-injector for DI

## Status

Accepted (current implementation)

## Context

`dependency-injector` containers and per-request session scoping are implemented across the bounded contexts. Each context has one container, a module-level global container instance, API router wiring, and a per-request `session` override reset in `finally` (`backend/app/modules/checkout/api/routes.py` and `backend/app/modules/orders/api/routes.py`).

## Decision

Continue with `dependency-injector`: one container per bounded context, module-level global container, API router wiring, and per-request `session` override reset in `finally`.

## Options considered

| Option | Assessment |
|--------|------------|
| Manual constructor injection | Zero dependencies, but more boilerplate in routes and tests. |
| dependency-injector | Implemented for orders, inventory, payments, notifications, and checkout; supports scoped overrides and fits the module layout. |
| Another DI framework | Would add migration cost without clear gain over the current library. |

## Consequences

- **Positive**: consistent wiring pattern across modules; request-scoped sessions keep units of work clean.
- **Negative**: containers must be created for all modules before the pattern is usable across contexts.
- **Neutral**: tests can override providers at the container boundary.

## References

- [ARCHITECTURE.md](../../ARCHITECTURE.md) — Cross-cutting concerns / DI container strategy
- `backend/app/modules/orders/api/container.py`
- `backend/app/modules/orders/api/routes.py`
- `backend/app/modules/inventory/api/container.py`
- `backend/app/modules/payments/api/container.py`
- `backend/app/modules/notifications/api/container.py`
- `backend/app/modules/checkout/api/container.py`
- `backend/app/app.py` — container `wire()` wiring
