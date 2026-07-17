# Apply Progress: Reconstruct Project Foundation

## Status

- **Change**: reconstruct-project-foundation
- **Artifact store**: openspec
- **Mode**: Strict TDD
- **Current branch**: `docs/w6-design`
- **Parent branch**: `docs/w5-adrs` @ cabe066
- **Tracker branch**: `feat/foundation-docs`
- **Slice**: W6 DESIGN target UX + validation
- **Completed tasks**: 0.1, 0.2, 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4a.1, 4a.2, 4b.1, 4b.2, 5.1, 5.2, 6.1, 6.2 (16/21)
- **Total tasks**: 21

## Completed Tasks

- [x] 0.1 Per excluded path capture: VCS status → `paths.status`; sha256 → `paths.sha256`; untracked listing; `SUMMARY.txt` at `$(git rev-parse --git-common-dir)/gentle-ai/sdd-baselines/reconstruct-project-foundation/`.
- [x] 0.2 Confirm regenerable from `feat/phase1-config-di-refactor`, outside product artifacts, not tracked.
- [x] 1.1 Replace `README.md`: pitch, Now/MVP/Future status, 5-min quick path, repo layout, doc index, contribution pointer.
- [x] 1.2 Validate: headings; links resolve; `markdownlint` clean.
- [x] 2.1 Create `PRD.md`: Vision, Problem, Personas, Journeys, MVP Target, Business rules, Non-goals, Metrics, Glossary pointer.
- [x] 2.2 Validate: ≥2 personas; MVP lists every commerce context; no present-tense for AMQP/catalog; `markdownlint` clean.
- [x] 3.1 Create `docs/GLOSSARY.md`: Usage, Domain terms, Events table (5 rows, producer+consumer), State vocabulary, Maintenance rule.
- [x] 3.2 Validate: event rows == ordered `Literal[...]` in `backend/app/shared/messaging/envelope.py`.
- [x] 4a.1 Create `ARCHITECTURE.md` narrative: Overview, Topology, Bounded contexts, Patterns, ADR index (planned paths), DESIGN link.
- [x] 4a.2 Validate: ADR index planned paths; DESIGN link planned; Mermaid `flowchart LR` present and scoped to W4a.
- [x] 4b.1 Extend `ARCHITECTURE.md`: Cross-cutting concerns, NFRs, Current Implementation Status matrix with `Decision | Horizon | Status | Code evidence | Doc location`, `sequenceDiagram`, `stateDiagram-v2`.
- [x] 4b.2 Validate: matrix status ∈ {implemented, partial, target}; partials never present-tense; Mermaid blocks present and honest about AMQP target state.
- [x] 5.1 Create `docs/adr/README.md` + 5 ADRs (`0001..0005-use-*.md`): Title, Status, Context, Decision, Options considered, Consequences, References.
- [x] 5.2 Validate: 5 files exist; structure per ADR; index matches filenames; statuses are honest; no target ADR claims implemented; references link to canonical docs.
- [x] 6.1 Create `DESIGN.md`: YAML tokens, prominent Target-design notice, Overview, Flows with Now/Target columns, Screen inventory, Colors, Typography, Layout, States, Accessibility, Components, Do/Don't; one `flowchart TD` checkout success/failure/pending journey.
- [x] 6.2 Validate: Target header present; only Now column uses present-tense; no duplicated backend diagrams; required links to PRD, ARCHITECTURE, GLOSSARY, and ADR index resolve; async status vocabulary links to GLOSSARY; accessibility and responsive requirements covered; `mmdc` equivalent static checks pass.

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `README.md` | Modified | Replaced 1-line placeholder with blueprint README |
| `PRD.md` | Created | Product Requirements Document with vision, personas, MVP scope, business rules, non-goals, and metrics |
| `docs/GLOSSARY.md` | Created | Canonical domain/event vocabulary, bounded contexts, event table, state transitions, maintenance rules |
| `ARCHITECTURE.md` | Created / Modified | W4a narrative topology diagram, bounded contexts, patterns, ADR index placeholder, DESIGN link; W4b cross-cutting concerns, measurable NFRs, current implementation status matrix, sequenceDiagram, stateDiagram-v2 |
| `docs/adr/README.md` | Created | ADR index: purpose, status rules, numbered index, Now/MVP Target/Future interpretation |
| `docs/adr/0001-use-shared-event-store.md` | Created | ADR for shared event store vs per-module tables |
| `docs/adr/0002-use-choreography.md` | Created | ADR for event choreography + outbox/idempotency; why not orchestrated saga initially |
| `docs/adr/0003-use-dependency-injector.md` | Created | ADR for module DI containers, global composition, per-request session override |
| `docs/adr/0004-own-iam-context.md` | Created | ADR for owned IAM bounded context with JWT registration/login/roles |
| `docs/adr/0005-use-deterministic-simulated-payments.md` | Created | ADR for deterministic simulated payment provider behind ports/adapters |
| `DESIGN.md` | Created | Target UX flows, screen inventory, machine-readable YAML design tokens, component states, accessibility rules, and Do/Don't guidance |
| `openspec/changes/reconstruct-project-foundation/tasks.md` | Modified | Marked W6 tasks complete |
| `openspec/changes/reconstruct-project-foundation/apply-progress.md` | Modified | Merged W6 evidence into cumulative progress |

## TDD Cycle Evidence

| Task | Test File / Validation | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|------------------------|-------|------------|-----|-------|-------------|----------|
| 0.1 | `/tmp/opencode/capture_baseline.py` | Operational | N/A (new) | ✅ Empty baseline | ✅ 259 paths captured | ✅ Regenerated after counting fix | ✅ Fixed deletion counting |
| 0.2 | `/tmp/opencode/compare_baseline.py` | Operational | N/A (new) | ✅ Initial mismatches | ✅ 259 paths verified | ✅ Re-ran after parser fix | ✅ Normalized token parsing |
| 1.1 | `/tmp/opencode/validate_w1_readme.py` | Static/docs | N/A (new) | ✅ Failed on placeholder | ✅ Passed | ✅ Multiple sections checked | ✅ README tightened |
| 1.2 | `/tmp/opencode/validate_w1_readme.py` | Static/docs | N/A (new) | ✅ Failed on placeholder | ✅ Passed | ✅ Planned links accepted | ✅ Validator refined |
| 2.1 | `/tmp/opencode/validate_w2_prd.py` | Static/docs | N/A (new) | ✅ Failed: PRD.md not found | ✅ Passed | ✅ Personas, contexts, payment stub, IAM, patterns | ✅ PRD tightened |
| 2.2 | `/tmp/opencode/validate_w2_prd.py` | Static/docs | N/A (new) | ✅ Failed: missing required headings | ✅ Passed | ✅ Added AMQP/catalog live-claim + triangulation checks | ✅ Validator refined |
| 3.1 | `/tmp/opencode/validate_w3_glossary.py` | Static/docs | N/A (new) | ✅ Failed: GLOSSARY.md not found | ✅ Passed | ✅ Event order, producers/consumers, contexts, state transitions | ✅ GLOSSARY tightened |
| 3.2 | `/tmp/opencode/validate_w3_glossary.py` | Static/docs | N/A (new) | ✅ Failed: section regex matched only headings | ✅ Passed | ✅ Added envelope.py + services.py AST extraction | ✅ Validator switched to line-based section parser |
| 4a.1 | `/tmp/opencode/validate_w4a_architecture.py` | Static/docs | N/A (new) | ✅ Failed: ARCHITECTURE.md not found | ✅ Passed | ✅ Required sections, links, Mermaid LR, ADR filenames, horizon terms | ✅ ARCHITECTURE.md tightened |
| 4a.2 | `/tmp/opencode/validate_w4a_architecture.py` | Static/docs | N/A (new) | ✅ Failed: W4b diagrams present in W4a | ✅ Passed | ✅ Added scope guard for sequenceDiagram/stateDiagram-v2, partial honesty checks | ✅ Validator tightened |
| 4b.1 | `/tmp/opencode/test_w4b_architecture.py` | Static/docs | ✅ W4a 10/10 | ✅ Failed: missing matrix/diagrams/NFRs | ✅ Passed after W4b edit | ✅ Matrix rows, evidence paths, diagrams | ✅ Content tightened, validator normalized separators |
| 4b.2 | `/tmp/opencode/test_w4b_architecture.py` | Static/docs | ✅ W4a 10/10 | ✅ Failed: status enums/horizon notes | ✅ Passed after W4b edit | ✅ State transitions, NFR tags, cross-links | ✅ Validator refined |
| 5.1 | `/tmp/opencode/test_w5_adrs.py` | Static/docs | N/A (new) | ✅ Failed: docs/adr/README.md and ADRs missing | ✅ 8 passed after W5 edit | ➖ Skipped — docs-only structural creation; 5 files covered | ✅ Drafted concise ADRs |
| 5.2 | `/tmp/opencode/test_w5_adrs.py` | Static/docs | N/A (new) | ✅ Failed: no ADR files | ✅ 8 passed after W5 edit | ➖ Skipped — validation is a single structural scenario | ✅ Test refactored to allow root-doc links |
| 6.1 | `/tmp/opencode/test_w6_design.py` | Static/docs | N/A (new) | ✅ Failed: DESIGN.md not found | ✅ 17 passed after DESIGN.md edit | ✅ Required headings, token families, screen inventory columns, async status vocabulary | ✅ Added bounded-context reference in Overview |
| 6.2 | `/tmp/opencode/test_w6_design.py` | Static/docs | N/A (new) | ✅ Failed: target notice wording | ✅ 17 passed after DESIGN.md edit | ✅ Frontend absence, present-tense guard, backend diagram duplication guard | ✅ Validator tightened |

## Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command and exact result | `rtk pytest /tmp/opencode/test_w6_design.py -q` → `17 passed` |
| Runtime harness command/scenario and exact result | N/A — documentation-only W6 slice; no runtime boundary |
| Rollback boundary | `rm DESIGN.md` reverts the W6 delta without touching W0–W5 docs or excluded backend work |

## Validation Commands and Results

| Command | Result |
|---|---|
| `rtk pytest /tmp/opencode/test_w6_design.py -q` | `17 passed` |
| `rtk git diff --stat HEAD -- backend/ .github/ frontend/ openspec/config.yaml skills-lock.json` | empty — no excluded path changed |
| `rtk git diff --stat HEAD -- DESIGN.md` | 284 lines added |
| `rtk wc -l DESIGN.md` | 284 |

## Baseline Verification

- **Baseline directory**: `$(git rev-parse --git-common-dir)/gentle-ai/sdd-baselines/reconstruct-project-foundation/`
- **Excluded paths captured**: 259
- **Post-W6 worktree check**: `git diff HEAD -- backend/ .github/ frontend/ openspec/config.yaml skills-lock.json` is empty; no excluded path content or status changed in this worktree.
- **Conclusion**: W6 touched only `DESIGN.md` and OpenSpec progress files; no excluded path content or status changed.

## CodeGraph Evidence

CodeGraph exploration of the current worktree base verified the following current-state claims relevant to `DESIGN.md`:

- **No frontend implementation**: CodeGraph has no React, Vue, Angular, Svelte, Next.js, Nuxt, `index.html`, `main.ts`, `App.tsx`, or equivalent frontend entry points. The `frontend/` directory does not exist in the worktree.
- **Backend remains unchanged by W6**: W6 did not create, modify, or delete any file under `backend/app/`, `.github/`, or other excluded paths.
- **No IAM/catalog/cart UI code**: No `iam`, `catalog`, or `cart` modules exist in `backend/app/`, consistent with the Target-only columns in the screen inventory and flows.

## Deviations from Design

None — W6 implementation matches `design.md` and `spec.md`. `DESIGN.md` is explicitly tagged as a target design document; only its Now column is described in present tense.

## Issues Found

- `markdownlint-cli` and `mmdc` are not installed in this environment. W6 validation uses equivalent static pytest checks (file existence, required headings, target-notice wording, YAML token families, link targets, screen-inventory columns, Mermaid block presence, accessibility and responsive keywords, and backend-diagram duplication guard) consistent with W1–W5.
- `frontend/` does not exist in the worktree; the README already describes it as reserved for future work, and `DESIGN.md` does not claim a frontend exists.
- The durable baseline captured in W0 reflects the original repository's dirty refactor state (Target). The clean worktree `/home/jona/projects/eventcommerce-worktrees/w4b-recovery` represents published Git (Now); excluded-path diff against its own HEAD is empty, confirming W6 did not disturb the Now baseline.

## Remaining Tasks

- [ ] 7.1 Cross-link: `lychee --offline <all>` resolves.
- [ ] 7.2 Contract: event vocab == ordered `Literal[...]`; state == `pending→{pending,confirmed,cancelled}` idempotent; contexts/stack match spec.
- [ ] 7.3 Horizon + matrix: no present-tense on `partial`/`target`; matrix rows carry Horizon + Status + Code-evidence.
- [ ] 7.4 Quality + budget: `markdownlint` clean; `mmdc` all; per PR `git diff --stat` ≤400 (excl. generated diagrams).
- [ ] 7.5 Baseline closure: status set == `paths.status`; per-path sha256 == `paths.sha256`; no add/remove/rename/status-change.

## Workload / PR Boundary

- **Mode**: feature-branch-chain
- **Current work unit**: W6 DESIGN target UX + validation
- **Branch**: `docs/w6-design` based on `docs/w5-adrs` @ cabe066
- **Child PR target**: `docs/w5-adrs` (immediate parent; never `main` directly)
- **Boundary**: Starts after W5 ADR validation; ends with `DESIGN.md` and W6 validation
- **Estimated review budget impact**: W6 delta ≈284 new lines in `DESIGN.md` plus OpenSpec progress updates, well under the 400-line review gate

## Next Recommended

`sdd-verify` for W6, then proceed to W7 cross-link/contract/baseline closure.
