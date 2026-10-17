# ADR 0007: Harden credentials and dependencies

## Status

Mixed — each decision carries its true state:

- Rate limiting on register/login: **Accepted (current implementation)** (delivered in this branch).
- Dependency remediation: **Accepted (current implementation)** (delivered in this branch).
- Refresh-token rotation: **Partially implemented** — decided and implemented on `feat/iam-refresh-rotation`, **not merged**: its native review cannot close while the reviewer provider is out of credits. Nothing in this branch serves `POST /api/v1/iam/refresh`.
- React Router 7 bump: **Accepted (current implementation)** — delivered as `react-router-dom` 7.18.4 (PR #112). A clean version bump with **no source change**, closing the two advisories and taking `npm audit` from 2 moderate to 0.

## Context

The operator-console chain left five security pendings: two moderate React Router advisories (closable only by a major bump), no rate limiting on register/login, and no refresh-token rotation. The read-only security review found the React Router advisories **not reachable** in this client-only Vite SPA (no SSR or hydration entry point; no user-controlled navigation destination), `source-map-js` is transitive build tooling, and the backend advisories (`PyJWT`, `Mako`, `Multidict`) are not on a reachable path either (`verify_token` pins `algorithms=["HS256"]`, requires `exp`/`iss`/`aud`/`sub`, checks `purpose`, and fails closed on empty config; `Mako` arrives only through Alembic templating). Remediation is therefore hygiene and cadence, not incident response.

## Decision

D1 — Rate-limit the two credential routes with a settings-driven, in-process sliding-window limiter (`backend/app/modules/iam/api/rate_limit.py`), enforced as a FastAPI dependency on `POST /api/v1/iam/register` and `POST /api/v1/iam/login`. Login gets two budgets — per-account (`login:{host}:{email}`) plus per-origin (`login-host:{host}`) — and registration gets one per-origin budget (`register:{host}`). The per-account bucket is checked first so its established wait is kept, and both buckets share one generic detail so a rejection does not reveal which budget tripped. Past the limit the route answers `429` with a `Retry-After` header in whole seconds. Accepted defaults: 10 login attempts and 60 per-origin login attempts per 60-second window, 20 registrations per 60-second window (`EVENTCOMMERCE_LOGIN_RATE_LIMIT_ATTEMPTS`, `EVENTCOMMERCE_LOGIN_RATE_LIMIT_HOST_ATTEMPTS`, `EVENTCOMMERCE_LOGIN_RATE_LIMIT_WINDOW_SECONDS`, `EVENTCOMMERCE_REGISTER_RATE_LIMIT_ATTEMPTS`, `EVENTCOMMERCE_REGISTER_RATE_LIMIT_WINDOW_SECONDS`).

D2 — Keep limiter state on the FastAPI app instance (`request.app.state`), never a module global, so buckets cannot leak between apps and each fresh app starts with empty buckets. Entries are pruned on every check so buckets stay bounded.

D3 — Rotate refresh tokens server-side once the rotation unit merges: opaque high-entropy values (`secrets.token_urlsafe`) stored only as SHA-256, one family per login, exchange consumes the token, replaying a consumed token revokes the whole family, consumption is atomic so a concurrent double-spend cannot let two rotations win, successors inherit the family's absolute expiry, and every failure is one generic `401`. A slow KDF was deliberately not used: unlike a password, the value already carries full entropy, so a KDF buys nothing and only adds per-request cost. Login widens to `access_token` + `refresh_token` plus `POST /api/v1/iam/refresh`; the frontend refreshes once on a 401, retries the original request, and only clears the session if that also fails. This does **not** fix the stored-credential exposure — it moves the same limitation to a longer-lived token — which is why moving to an `HttpOnly` cookie ranks above it.

D4 — Remediate dependencies in the lock plus floors in the manifest: the W1 bumps (`PyJWT` → 2.15.1, `Mako`, `Multidict` 7.1.0) are pinned by minimums in `backend/app/tests/shared/test_dependency_pins.py`, so a regenerated lock cannot silently re-resolve a flagged release, and the `pyjwt` floor was raised to `>=2.15.1` in `backend/pyproject.toml` so the resolver refuses the old release. `source-map-js` stays lock-only (transitive build tooling, no manifest floor). "Closed" here means the flagged versions no longer resolve — no backend advisory scanner exists in this repository to sign off.

D5 — Take the React Router 7 major bump as staying current, not as closing an exposure: the two advisories it closes were found unreachable in this SPA, so no claim of an averted incident is made.

## Options considered

| Option | Assessment |
|--------|------------|
| Shared rate-limit store (Redis) | Rejected: no Redis exists, no throttling middleware, and no multi-replica deployment to justify it. |
| Global rate-limit middleware | Rejected: keeps the blast radius on the two credential routes instead of touching every route. |
| Slow KDF for stored refresh tokens | Rejected: the token value already carries full entropy, so a KDF adds per-request cost with no security gain. |
| Closing the React Router advisories without the major bump | Rejected: 7.x is the only path that closes them; the bump is staying current on an unreachable finding. |
| Server-side logout in this chain | Rejected: an R1 review finding, and S4 asks for findings to be reported rather than implemented. Storage introduced by rotation makes revocation possible later. |

## Consequences

- **Positive**: credential guessing is bounded per account and per origin with a documented, configurable budget; remediated releases cannot silently return through lock regeneration; refresh-token replay becomes detectable and revocable once that unit merges.
- **Negative (accepted residual risk)**: the access token lives in `localStorage`, so XSS can read it — rotation moves the same exposure to a longer-lived token rather than fixing it. There is **no server-side logout**: clearing the session leaves the token valid until expiry (a review finding, deliberately not implemented in this chain). The limiter is per process, so more than one replica multiplies the effective budget; the origin is `request.client.host`, so **behind a reverse proxy every caller shares the proxy's ceiling**. No backend CVE scanner is configured, so dependency "closed" means the flagged versions no longer resolve.
- **Neutral**: the pin tests assert minimums, not exact locked versions, so a later legitimate upgrade keeps passing.

## References

- [PRD.md](../../PRD.md) — Non-goals / IAM abuse controls
- [GLOSSARY.md](../GLOSSARY.md) — credential rate-limit budget, refresh-token family
- `backend/app/modules/iam/api/rate_limit.py` — limiter, budgets, `429` + `Retry-After`
- `backend/app/shared/config/settings.py` — `login_rate_limit_*` / `register_rate_limit_*` settings and aliases
- `backend/app/tests/shared/test_dependency_pins.py` — regression pins on the remediated releases
- `backend/pyproject.toml` — `pyjwt>=2.15.1` floor
