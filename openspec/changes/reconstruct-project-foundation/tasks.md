# Tasks: Reconstruct Project Foundation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~1750–2070 (excl. generated diagrams), 7 PR slices |
| 400-line budget risk | High — chained PRs each ≤400 |
| Chained PRs recommended | Yes |
| Suggested split | W0→W1→W2→W3→W4a→W4b→W5→W6→W7 |
| Delivery strategy | auto-forecast (chain strategy: feature-branch-chain) |
| Chain strategy | feature-branch-chain (tracker branch) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units (each slice ≤400 lines max; runtime harness = N/A — docs only)

| Unit | Max | Focused test command | Rollback boundary |
|------|-----|----------------------|-------------------|
| W0  | 0   | per-excluded-path sha256 vs `paths.sha256`; status vs `paths.status` | N/A — operational, not committed |
| W1  | 250 | `markdownlint README.md`; `lychee --offline README.md` | revert `README.md` only |
| W2  | 400 | `markdownlint PRD.md`; `lychee --offline PRD.md` | revert `PRD.md` only |
| W3  | 200 | `markdownlint docs/GLOSSARY.md`; event-vocab == ordered `Literal[...]` | revert `docs/GLOSSARY.md` only |
| W4a | 320 | `markdownlint ARCHITECTURE.md`; `mmdc` `flowchart LR` | revert narrative only |
| W4b | 400 | matrix status ∈ {implemented,partial,target}; `mmdc` all | revert delta only |
| W5  | 350 | `markdownlint docs/adr/**/*.md`; 5 files; index matches | revert `docs/adr/` only |
| W6  | 400 | `markdownlint DESIGN.md`; `mmdc` `flowchart TD` | revert `DESIGN.md` only |
| W7  | 0   | `lychee --offline <all>`; matrix valid; `mmdc` all; baseline closure | (no commit) fix prior PRs |

Chain bases (feature-branch-chain): tracker `feat/foundation-docs` (draft, no-merge) accumulates final integration; W1→`feat/foundation-docs`, W2→`.../w1-readme`, W3→`.../w2-prd`, W4a→`.../w3-glossary`, W4b→`.../w4a-arch-narrative`, W5→`.../w4b-arch-matrix`, W6→`.../w5-adr`; W7 verify gate, no PR. Only the tracker merges to main. If a child PR shows previous PR changes, its base is wrong — retarget or rebase before review.

## Phase 0: Baseline Snapshot (W0, apply precondition)

S12 excluded path set: backend app/config/test, alembic, conftest, env, Docker, `.github/**`, `frontend/**`, `openspec/config.yaml`, `skills-lock.json`, pending refactor on `feat/phase1-config-di-refactor` (no revert/format/cleanup). Full enumeration in spec R9.

- [x] 0.1 Per excluded path capture: VCS status → `paths.status`; sha256 → `paths.sha256`; untracked listing; `SUMMARY.txt` at `$(git rev-parse --git-common-dir)/gentle-ai/sdd-baselines/reconstruct-project-foundation/`.
- [x] 0.2 Confirm regenerable from `feat/phase1-config-di-refactor`, outside product artifacts, not tracked.

Baseline gate (S12): every W1–W6 PR open verifies status set == `paths.status` AND per-path sha256 == `paths.sha256`; W7 re-verifies + asserts no add/remove/rename/status-change.

## Phase 1: README (W1, PR 1, ≤250)

- [x] 1.1 Replace `README.md`: pitch, Now/MVP/Future status, 5-min quick path, repo layout, doc index, contribution pointer.
- [x] 1.2 Validate: headings; links resolve; `markdownlint` clean.

## Phase 2: PRD (W2, PR 2, ≤400)

- [ ] 2.1 Create `PRD.md`: Vision, Problem, Personas, Journeys, MVP Target, Business rules, Non-goals, Metrics, Glossary pointer.
- [ ] 2.2 Validate: ≥2 personas; MVP lists every commerce context; no present-tense for AMQP/catalog; `markdownlint` clean.

## Phase 3: GLOSSARY (W3, PR 3, ≤200)

- [ ] 3.1 Create `docs/GLOSSARY.md`: Usage, Domain terms, Events table (5 rows, producer+consumer), State vocabulary, Maintenance rule.
- [ ] 3.2 Validate: event rows == ordered `Literal[...]` in `backend/app/shared/messaging/envelope.py`.

## Phase 4: ARCHITECTURE narrative (W4a, PR 4, ≤320)

- [ ] 4a.1 Create `ARCHITECTURE.md` core: Overview, Topology (`flowchart LR`), Bounded contexts, Patterns, ADR index (planned paths), DESIGN link.
- [ ] 4a.2 Validate: ADR index planned paths; DESIGN link planned; `mmdc` renders.

## Phase 5: ARCHITECTURE matrix + diagrams (W4b, PR 5, ≤400)

- [ ] 4b.1 Extend `ARCHITECTURE.md`: Cross-cutting, NFRs, Current Implementation Status matrix, `sequenceDiagram`, `stateDiagram-v2`.
- [ ] 4b.2 Validate: matrix status ∈ {implemented, partial, target}; partials never present-tense; `mmdc` all.

## Phase 6: ADR seed + index (W5, PR 6, ≤350)

- [ ] 5.1 Create `docs/adr/README.md` + 5 ADRs (`0001..0005-use-*.md`): Title, Status, Context, Decision, Consequences, Options, References.
- [ ] 5.2 Validate: 5 files exist; structure per ADR; index matches filenames.

## Phase 7: DESIGN (W6, PR 7, ≤400)

- [ ] 6.1 Create `DESIGN.md`: YAML tokens, Target notice, Overview, Flows (Now/Target), Screen inventory, Colors, Typography, Layout, States, a11y, Components, Do/Don't; one `flowchart TD` checkout/error flow.
- [ ] 6.2 Validate: Target header; only Now column present-tense; no duplicative diagrams; `mmdc` renders.

## Phase 8: Cross-link + Contract + Baseline Closure (W7, verify gate, no PR)

- [ ] 7.1 Cross-link: `lychee --offline <all>` resolves.
- [ ] 7.2 Contract: event vocab == ordered `Literal[...]`; state == `pending→{pending,confirmed,cancelled}` idempotent; contexts/stack match spec.
- [ ] 7.3 Horizon + matrix: no present-tense on `partial`/`target`; matrix rows carry Horizon + Status + Code-evidence.
- [ ] 7.4 Quality + budget: `markdownlint` clean; `mmdc` all; per PR `git diff --stat` ≤400 (excl. generated diagrams).
- [ ] 7.5 Baseline closure: status set == `paths.status`; per-path sha256 == `paths.sha256`; no add/remove/rename/status-change.
