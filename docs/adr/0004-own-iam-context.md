# ADR 0004: Own IAM as a bounded context

## Status

Accepted (MVP Target)

## Context

There is no authentication or authorization code today. The portfolio goal is to demonstrate an end-to-end commerce backend, including JWT role-based access, not just to call an external IdP.

## Decision

Build IAM as an owned `iam` bounded context with JWT registration, login, and role authorization. Roles will be carried in the JWT and enforced at API boundaries by FastAPI dependencies.

## Options considered

| Option | Assessment |
|--------|------------|
| External IdP | Less code, but hides the auth boundary from the portfolio and couples secrets to a third party. |
| Cross-cutting JWT middleware | Simpler routing, but role logic drifts away from the domain. |
| Owned `iam` bounded context | Demonstrates auth as a real domain, keeps roles explicit, and matches the portfolio goal. |

## Consequences

- **Positive**: auth is a first-class domain; role enforcement is visible and testable.
- **Negative**: more code to write and maintain; secret/key management is required.
- **Neutral**: migration to an external IdP later is possible without changing the API role contract.

## References

- [PRD.md](../../PRD.md) — MVP Target / IAM
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — Bounded contexts / Security and auth boundaries
- [GLOSSARY.md](../GLOSSARY.md) — bounded context
