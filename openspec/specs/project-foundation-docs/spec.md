# project-foundation-docs Specification

## Purpose

Governs the root doc set (`README`, `PRD`, `ARCHITECTURE`, `DESIGN`, `docs/GLOSSARY`, `docs/adr/`): per-doc ownership, Now/MVP Target/Future honesty, code-contract lock-in against verified current code.

## Requirements

### Requirement: Canonical Document Set and Navigation

Project MUST ship root `README.md`, `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md` + `docs/GLOSSARY.md` + `docs/adr/`. `README.md` MUST link to the other three root docs and top-level layout in its 5-min quick path.

#### Scenario: Canonical paths and README links

- GIVEN the change is merged; WHEN a reviewer lists canonical paths and README outbound links; THEN every path exists AND `README.md` links to each other root doc

### Requirement: Per-Document Ownership Principle

Each doc MUST own a unique area; cross-refs are links, not copies. The owned area per doc is the section matrix in R5.

#### Scenario: Each doc owns its area

- GIVEN the section matrix in R5; WHEN two docs cover the same area; THEN one owns it and the other cross-references via link

### Requirement: Now / MVP Target / Future Honesty Rule

Every capability claim MUST be tagged Now, MVP Target, or Future. `ARCHITECTURE.md` MUST include a Current Implementation Status matrix (Decision, Status `implemented`/`partial`/`target`, Code evidence, Doc location). `DESIGN.md` is target; only its Now column binds. No present-tense for non-implemented capabilities.

#### Scenario: Status matrix and language are honest about partials

- GIVEN the AMQP consumer and outbox worker are not yet bootstrapped, and catalog does not exist; WHEN a reviewer reads the matrix and greps `PRD.md` + `ARCHITECTURE.md` for catalog and AMQP; THEN those rows carry Status `partial`/`target` with code-evidence pointers AND no sentence uses present-tense business language implying they are live

### Requirement: Code-Contract Lock-In — Source Hierarchy

Docs MUST honor the source hierarchy. Published Git Now is the binding reference for current-state claims. MVP Target contracts are sourced from the dirty refactor branch.

#### Now (Published Git)

| Contract | Value | Evidence |
|---|---|---|
| Current Events | `OrderCreated` (orders), `InventoryReserved` (inventory), `PaymentAuthorized` (payments), `OrderNotificationSent` (notifications) | `backend/app/modules/*/domain/events/*.py` per-module dataclasses |
| State Machine | `pending→{inventory_reserved,cancelled}`, `inventory_reserved→{payment_authorized,cancelled}`, `payment_authorized→{confirmed,cancelled}` | `backend/app/modules/orders/domain/services/order_domain_service.py` `can_transition()` |
| No shared infra | No envelope, outbox, idempotency, DI containers, RabbitMQ, or `aio-pika` | `backend/app/shared/` has only `config/` and `db/` |
| Current Contexts | `orders`, `inventory`, `payments`, `notifications` | `backend/app/modules/` |
| Stack | Py3.13+, FastAPI, SQLAlchemy 2 async, Pydantic Settings 2.x, Alembic, `uv` | Published code |

#### MVP Target (source: dirty refactor branch)

| Contract | Value |
|---|---|
| Target Events | `InventoryRejected`, `OrderConfirmed`, `OrderCancelled` (shared envelope) |
| Target Contexts | `iam`, `catalog`, `cart` |
| Target Stack | `dependency-injector`, `aio-pika`, shared event store, outbox, idempotency store |

A current-capability claim MUST be backed by an existing `backend/app/` file in the published tree; otherwise the claim is tagged MVP Target.

#### Scenario: Current event vocabulary matches published per-module classes

- GIVEN the docs list current event types; WHEN a reviewer checks each against the per-module `domain/events/*.py` dataclass names in the published tree; THEN the sets match exactly

#### Scenario: No invented current capability

- GIVEN a doc claims a current capability; WHEN a reviewer locates the implementing code; THEN the file exists in `backend/app/` in the published tree and is referenced in the status matrix, OR the claim is tagged Target

### Requirement: Product Contract

`PRD.md` MUST declare the project a technical portfolio with product-quality realism (not toy demo, not commercial). MVP MUST cover IAM (owned context, JWT, reg/login/role auth), catalog, cart, checkout, orders, inventory, simulated payments, notifications. Event coordination = choreography + transactional outbox + idempotent consumers. Payments = real bounded context behind ports/adapters with a deterministic simulated provider for MVP (no random outcomes as business behavior).

#### Scenario: PRD declares nature, scope, and coordination model

- GIVEN a reviewer opens `PRD.md`; WHEN they read Vision, MVP, and payments; THEN the project is named technical portfolio with product-quality realism, MVP lists each commerce context, the outbox + choreography + idempotency model is named, AND payments are deterministic simulated behind a real bounded context

### Requirement: Required Sections per Document

Each root doc MUST contain its required sections. Section matrix (each doc owns only its row): `README`=pitch,quick-path,layout,index,contribution-pointer; `PRD`=vision,problem,personas,journeys,MVP,rules,non-goals,metrics,glossary-pointer; `ARCHITECTURE`=topology,contexts,patterns,cross-cutting,NFRs,status-matrix,ADR-index; `DESIGN`=target-header,flows(Now/Target),screen-inventory,tokens,states,a11y; `GLOSSARY`=domain terms+event entries; `ADR`=title,status,context,decision,consequences (1/file). `docs/GLOSSARY.md` MUST list each of the 7 governed event types (4 Now + 3 MVP Target) with producer and consumer. `docs/adr/` MUST seed ≥1 ADR per: shared event store, choreography over saga, `dependency-injector`, IAM bounded context, deterministic simulated payments.

#### Scenario: Overlapping claims are linked, not duplicated

- GIVEN a fact in `PRD.md` overlaps an area owned by `ARCHITECTURE.md`; WHEN a reviewer searches both; THEN the fact appears in `PRD.md` AND `ARCHITECTURE.md` references it via link, not verbatim copy

#### Scenario: GLOSSARY and ADR seed cover the contract

- GIVEN `docs/GLOSSARY.md` and `docs/adr/` are read; WHEN a reviewer checks the 7 governed event types (4 Now + 3 MVP Target) and 5 named decisions; THEN each event has a row (producer + consumer) AND each decision has a seeded ADR

### Requirement: Cross-Links and Maintainability

`README.md` MUST link to the other three root docs. `ARCHITECTURE.md` MUST link to `docs/adr/` and `DESIGN.md`. Each root doc MUST link to `docs/GLOSSARY.md` for any domain or event term. A code-contract change (event name, order state, context name, stack component) MUST update `docs/GLOSSARY.md` and any affected root doc in the same change.

#### Scenario: Cross-link round trip resolves

- GIVEN the docs are merged; WHEN a reviewer follows `README → PRD → GLOSSARY`, `ARCHITECTURE → ADR`, `ARCHITECTURE → DESIGN`; THEN every link resolves to an existing anchor or file AND no chain is broken

### Requirement: Authorship Order, 400-Line Gate, and Link Resolution

Each root doc diff MUST fit ≤400 lines (excl. generated diagrams). Authorship order `README → PRD → ARCHITECTURE → DESIGN` governs sequencing only — NOT link direction. Links MAY reference canonical planned paths from slice 1; by completion, every link MUST resolve. PR topology is `sdd-tasks`-decided; no PR count or branch plan is pre-committed.

#### Scenario: All cross-doc links resolve at completion

- GIVEN the change is merged; WHEN a reviewer follows every cross-doc link in every root doc; THEN every link resolves to an existing anchor or file, regardless of authorship order

#### Scenario: Each slice under 400 lines

- GIVEN a reviewer measures each root doc slice diff; WHEN they count added + removed lines per slice; THEN no slice exceeds 400 lines excluding generated diagrams

### Requirement: Excluded Surfaces

MUST NOT modify: `backend/app/**`, `backend/README.md`, `backend/pyproject.toml`, `backend/.env*`, `backend/Dockerfile`, `backend/docker-compose.yml`, `backend/alembic/**`, `backend/conftest.py`, any test file, `.github/**`, `frontend/**`, `openspec/config.yaml`, `skills-lock.json`, or pending refactor on `feat/phase1-config-di-refactor` (no revert/format/cleanup).

#### Scenario: Excluded paths are preserved from a captured pre-apply baseline through every work unit and final closure

- GIVEN the change is not yet applied; WHEN a baseline of the excluded paths is captured (path set, VCS status per path, and content identity per path) and persisted outside the product artifacts; THEN the baseline exists, is regenerable from the current branch state, and is not tracked in the repository
- WHEN any work unit completes; THEN the excluded paths' VCS status set equals the baseline status set AND every excluded path's content identity equals its baseline identity
- WHEN the change reaches final closure; THEN the same equality holds AND no file under any excluded path has been added, removed, renamed, or had its status changed relative to the baseline
