# Proposal: Reconstruct Project Foundation

## Intent

The project root has a 1-line `README.md` and no `PRD.md`, `ARCHITECTURE.md`, or `DESIGN.md`. The backend already encodes real contracts — bounded contexts, event vocabulary, order state machine, transactional outbox + idempotency — that no document explains or governs. Without a foundation, reviewers, contributors, and future SDD changes lack a shared source of truth, and downstream code is written against unspoken assumptions: the surest way to misrepresent the project (e.g., documenting the not-yet-wired AMQP consumer as "live").

## Why Foundation Before Setup & Implementation

- Code without a governing PRD/ARCH drifts; the refactor on `feat/phase1-config-di-refactor` is already uncommitted and undocumented.
- The event vocabulary (`OrderCreated`, `InventoryReserved`, `InventoryRejected`, `OrderConfirmed`, `OrderCancelled`), order state machine (`pending|confirmed|cancelled`), and bounded-context names are pinned in code. Locking them in docs now prevents every later change from inventing a divergent vocabulary.
- Setup / CI / frontend follow-up slices must reference a stable product definition; authoring tooling first risks building for the wrong product.

## Scope

### In Scope
- Root `README.md` (replace placeholder), `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md` (all new).
- `docs/GLOSSARY.md` — justified: event names are a contract; a glossary is the single, non-overlapping home for domain + event vocabulary and prevents drift.
- `docs/adr/` seed + index — justified: ARCHITECTURE references decisions (shared event store, choreography, `dependency-injector`) the reader cannot reconstruct from code alone.
- Document responsibility table + cross-document contracts (what each doc owns, what it must NOT duplicate).
- Per-doc **Now / MVP Target / Future** honesty rule — never claim an unimplemented capability as current.

### Out of Scope (this change)
- No `backend/app/**`, no `backend/README.md`, no `pyproject.toml` / `.env` / `Dockerfile` / `docker-compose` / `alembic`, no `conftest.py` / tests, no `.github/**`, no `frontend/**` (empty). `openspec/config.yaml` only if OpenSpec requires it.
- No code, setup, frontend, or defect fixes (broken `shared/events/__init__.py` import, unbootstrapped AMQP consumer / outbox worker, empty containers).
- The `feat/phase1-config-di-refactor` branch state is preserved **untouched** — no commit, revert, format, or cleanup of its pending refactor.

## Capabilities

> Contract with `sdd-spec`. No `openspec/specs/` exist yet.

### New Capabilities
- `project-foundation-docs`: governs the root document set, per-document responsibilities, cross-document contracts (event vocabulary, bounded-context names, order state machine, stack), and the Now / MVP-Target / Future honesty rule that forbids claiming an unimplemented capability as current.

### Modified Capabilities
- None (no main specs exist to modify).

## Approach

Single change, per-doc deliverables authored in order **README → PRD → ARCHITECTURE → DESIGN** so later cross-references are stable (exploration Approach 3).

- **Contracts lock-in**: docs MUST honor the in-code event vocabulary and order state machine above; entities/fields and stack choices (Python 3.13, FastAPI, SQLAlchemy 2 async, `pydantic-settings`, `dependency-injector`, `aio-pika`, Alembic, `uv`) recorded as verified, not invented.
- **MVP framing (user-approved, locked)**: portfolio project with product-quality realism (not a toy demo, not initially a commercial operation). MVP = full commerce journey — IAM, catalog, cart, checkout, orders, inventory, simulated payments, notifications. Event coordination = choreography + transactional outbox + idempotent consumers. IAM = owned bounded context with JWT (registration / login / role authorization). Payments = real bounded context behind ports/adapters with a **deterministic** simulated provider for the MVP (no random outcomes as business behavior).
- **Honesty rule**: every doc distinguishes Now / MVP Target / Future. ARCHITECTURE carries a Current Implementation Status matrix per decision (`implemented` / `partial` / `target`) so partials (AMQP consumer, outbox worker) are never cited as live.
- `DESIGN.md` is explicitly a **target design** doc (frontend does not exist); only its Now column is binding.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `README.md` | Replaced | 1-line placeholder → entry point, 5-min quick path, links to PRD/ARCH/DESIGN, repo layout. |
| `PRD.md` | New | Vision, personas, MVP features, business rules, non-goals, metrics, glossary pointer. |
| `ARCHITECTURE.md` | New | Topology, bounded contexts, event patterns, NFRs, ADR index, status matrix. |
| `DESIGN.md` | New | Target UX flows, screen inventory, tokens, Now/Target columns. |
| `docs/GLOSSARY.md` | New | Domain + event vocabulary (single home). |
| `docs/adr/` | New | Seed ADRs + index referenced by ARCHITECTURE. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Documenting unwired AMQP / outbox as "live" | High | Status matrix + Now/MVP-Target/Future rule; partials never cited as current. |
| Docs drift from code vocabulary | High | Contracts lock-in: event set & state machine copied verbatim from code; glossary as single source. |
| Dirty branch `feat/phase1-config-di-refactor` blocks or forks foundation work | Medium | Preserve untouched; branch foundation docs off the same branch without touching its refactor; no revert/format. |
| Foundation exceeds 400-line review budget | High | Per-doc work units (chained PRs); see Delivery Forecast. |
| MVP framing bloats into a full commercial storefront | Medium | Non-goals explicit in PRD; MVP = portfolio realism, not a commercial operation. |
| `backend/README.md` drifts further while root docs ship | Low | ARCHITECTURE flags it as superseded; alignment scheduled in follow-up #2. |

## Delivery Forecast (auto-forecast, 400-line gate)

Each root doc is substantial (PRD/ARCH/DESIGN each ~250–400 lines). Forecast:

- `Decision needed before apply`: **Yes**
- `Chained PRs recommended`: **Yes**
- `400-line budget risk`: **High**

Plan: one work unit + one PR slice per document, authored in README → PRD → ARCH → DESIGN order. Chaining is confirmed in `sdd-tasks`; it is **not** asserted as one-PR-per-doc by default — it is justified here because per-doc size exceeds the gate. Optional ancillary docs (`docs/GLOSSARY.md`, `docs/adr/`) fold into the doc that most needs them or form a final small slice.

## Rollback Plan

Foundation docs are additive root files. Revert = delete `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md`, `docs/GLOSSARY.md`, `docs/adr/`, and restore `README.md` to `# eventcommerce`. No code is touched, so rollback is purely file deletion. Per-doc PR slices allow targeted revert of a single document.

## Dependencies

- None external. The foundation can be authored on the current branch without code changes. Every follow-up depends on this foundation for vocabulary and scope.

## Success Criteria

- [ ] Four root docs exist and link to each other consistently.
- [ ] Every doc distinguishes Now / MVP Target / Future; zero unimplemented capability claimed as current.
- [ ] Event vocabulary and order state machine in docs match code exactly.
- [ ] PRD has personas + explicit non-goals; ARCHITECTURE has a status matrix; DESIGN is tagged target.
- [ ] Each doc ships as a reviewable work unit within the 400-line gate.

## Staged Follow-Up Program

| # | Change | Depends on |
|---|--------|-----------|
| 1 | `integrate-development-environment` (deps, pre-commit, CI, `AGENTS.md`, Makefile, `.env.example`) | Foundation |
| 2 | `align-backend-readme-and-fix-stale-structure-doc` | Foundation |
| 3 | `fix-shared-events-broken-import-and-bootstrap-messaging` (broken import + outbox worker + AMQP consumer) | Foundation |
| 4 | `wire-inventory-payments-notifications-endpoints` | 3 |
| 5 | `mvp-core-flow-vertical-slice-e2e` (real AMQP e2e test) | 3, 4 |
| 6 | `add-catalog-bounded-context` | Foundation |
| 7 | `add-cart-bounded-context` | 6 |
| 8 | `add-iam-auth` (owned context, JWT) | Foundation |
| 9 | `add-saga-and-dlq` | 3 |
| 10 | `add-observability-and-runbooks` | 3 |
| 11 | `add-frontend-mvp` | 3–5 |

## Proposal Question Round

The five exploration product questions are resolved by the user-approved decisions (project nature, MVP scope, consistency model, IAM/JWT, deterministic simulated payments) — incorporated above as locked assumptions; no blocking round is needed. One optional confirmation point (not blocking): confirm `docs/GLOSSARY.md` and a seeded `docs/adr/` are in-scope (justified) versus deferred to follow-ups. No second round required unless you want to adjust scope.
