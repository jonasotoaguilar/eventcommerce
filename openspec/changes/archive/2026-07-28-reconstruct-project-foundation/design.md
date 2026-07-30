# Design: Reconstruct Project Foundation

## Technical Approach

Produce an evidence-led documentation system. Root-doc authorship is sequenced `README → PRD → ARCHITECTURE → DESIGN`; sequencing does not restrict link direction. Canonical planned paths may be linked immediately; closure must resolve all paths/anchors. Claims use **Now**, **MVP Target**, or **Future**.

## Architecture Decisions

| Option | Trade-off | Decision |
|---|---|---|
| Published Git (Now) vs dirty working tree (Target) | Dirty refactor has shared infra that does not exist in published Git | Published Git Now is binding for current-state claims; dirty refactor is MVP Target evidence only; `exploration.md` is historical snapshot against dirty tree, not Now evidence. Conflicts are classified by source hierarchy, never blended. |
| Duplicate context in every doc vs ownership | Links add navigation but prevent drift | One owner per fact; other documents use relative links to canonical headings. |
| Prose-only status vs explicit schema | Tables require maintenance but expose overclaims | Every capability is horizon-tagged; ARCHITECTURE carries the implementation matrix. |
| Broad diagram set vs question-driven diagrams | Fewer diagrams omit decoration, not information | Include only topology, event flow, state machine, and UX flow views listed below. |

## Document Blueprints and File Changes

| File / action | Responsibility | Required section order |
|---|---|---|
| `README.md` / Modify | Entry point and five-minute success | Pitch; Status snapshot; Quick path; Repository layout; Documentation index; Contribution pointer |
| `PRD.md` / Create | Product why, who, scope, and outcomes | Vision; Problem; Personas; Journeys; MVP Target; Business rules; Non-goals; Metrics; Glossary |
| `ARCHITECTURE.md` / Create | System structure and technical decisions | Overview; Topology; Bounded contexts; Patterns; Cross-cutting concerns; NFRs; Current Implementation Status; ADR index; DESIGN link |
| `DESIGN.md` / Create | Target UX and machine-readable visual contract | YAML tokens; Target-design notice; Overview; Flows (Now/Target); Screen inventory; Colors; Typography; Layout; States; Accessibility; Components; Do/Don’t |
| `docs/GLOSSARY.md` / Create | Canonical domain/event vocabulary | Usage; Domain terms; Events table (name, producer, consumer); State vocabulary; Maintenance rule |
| `docs/adr/README.md` / Create | ADR lifecycle and index | Purpose; Status rules; Numbered index |
| `docs/adr/0001..0005-*.md` / Create | Non-obvious decision rationale | Title; Status; Context; Decision; Consequences; Options; References |

ADR filenames are `0001-use-shared-event-store.md`, `0002-use-choreography.md`, `0003-use-dependency-injector.md`, `0004-own-iam-context.md`, and `0005-use-deterministic-simulated-payments.md`. Do not add ADRs for obvious framework, folder, or command facts.

## Interfaces / Contracts

The ARCHITECTURE matrix schema is `Decision | Horizon | Status | Code evidence | Doc location`, where status is exactly `implemented`, `partial`, or `target`. **Now** requires an existing `backend/app/` pointer in the published Git tree only; shared infrastructure (envelope, outbox, idempotency, DI containers, RabbitMQ) absent from published tree is `target` with Horizon `MVP Target`. IAM/catalog/cart and deterministic payment replacement are `target`. **Future** remains explicitly non-committed.

Link map: README → PRD/ARCHITECTURE/DESIGN; every root doc → GLOSSARY when using governed terms; ARCHITECTURE → ADR index/DESIGN; index ↔ ADRs.

Contract checks compare ordered current events (per-module dataclasses), order transitions (`can_transition`), current contexts, and stack against the published Git tree for Now, and against the spec for MVP Target. Product text preserves portfolio-quality full-commerce MVP, choreography + outbox + idempotency, owned JWT IAM, and deterministic simulated payments.

## Diagrams

ARCHITECTURE owns Mermaid `flowchart LR` topology, `sequenceDiagram` commerce event flow with partial/target labels, and `stateDiagram-v2` order transitions. DESIGN owns one `flowchart TD` shopper checkout/error-state flow. README, PRD, GLOSSARY, and ADRs contain no duplicative diagrams.

## Testing Strategy

| Check | Method |
|---|---|
| Structure/links | Assert required headings; resolve all relative files and anchors after completion. |
| Contracts/honesty | Compare ordered events and state transitions; require evidence for Now; scan AMQP/catalog/payment wording for horizon labels. |
| Quality/budget | Markdown lint; render every Mermaid block; reject duplicate anchors; count each root-doc slice additions + deletions at ≤400, excluding generated diagrams. |
| Scope | Snapshot dirty status before/after and assert no excluded path changed. |

## Work Units

Boundaries are README; PRD; GLOSSARY; ARCHITECTURE; ADR seed/index; DESIGN; final cross-link/validation closure. Each unit includes focused validation and rollback by owned files. `sdd-tasks` will forecast sizes and choose final PR topology under auto-forecast; this design does not pre-commit PR count.

## Spec Traceability

| Requirement / scenarios | Mechanism |
|---|---|
| R1/S1 | Blueprint + resolved README index |
| R2/S2 | Single-owner table and link-only reuse |
| R3/S3 | Horizon labels + status matrix |
| R4/S4–S5 | Code-backed contract checks |
| R5/S6 | Locked product contract |
| R6/S7–S8 | Exact sections, glossary rows, five ADRs |
| R7/S9 | Relative-link closure |
| R8/S10–S11 | Sequence-only authorship + line gate |
| R9/S12 | Dirty-tree snapshot and excluded-path diff |

## Threat Matrix

N/A — documentation only; no routing, shell, subprocess, VCS/PR automation, executable classification, or process-integration boundary is introduced.

## Migration / Rollout

No data migration. Current excluded-path diff versus `main` is non-empty; apply must validate a captured baseline and docs-only commit range while preserving every dirty backend, frontend, GitHub, and setup file byte-for-byte.

## Open Questions

None.
