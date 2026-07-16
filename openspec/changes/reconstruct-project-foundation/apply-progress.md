# Apply Progress: Reconstruct Project Foundation

## Status

- **Change**: reconstruct-project-foundation
- **Artifact store**: openspec
- **Mode**: Strict TDD
- **Current branch**: `docs/w3-glossary`
- **Tracker branch**: `feat/foundation-docs`
- **Slice**: W3 GLOSSARY
- **Completed tasks**: 0.1, 0.2, 1.1, 1.2, 2.1, 2.2, 3.1, 3.2 (8/21)
- **Total tasks**: 21
- **Changed lines**: 70 (`docs/GLOSSARY.md`: 70 new lines; `tasks.md`: 2 insertions)

## Completed Tasks

- [x] 0.1 Per excluded path capture: VCS status → `paths.status`; sha256 → `paths.sha256`; untracked listing; `SUMMARY.txt` at `$(git rev-parse --git-common-dir)/gentle-ai/sdd-baselines/reconstruct-project-foundation/`.
- [x] 0.2 Confirm regenerable from `feat/phase1-config-di-refactor`, outside product artifacts, not tracked.
- [x] 1.1 Replace `README.md`: pitch, Now/MVP/Future status, 5-min quick path, repo layout, doc index, contribution pointer.
- [x] 1.2 Validate: headings; links resolve; `markdownlint` clean.
- [x] 2.1 Create `PRD.md`: Vision, Problem, Personas, Journeys, MVP Target, Business rules, Non-goals, Metrics, Glossary pointer.
- [x] 2.2 Validate: ≥2 personas; MVP lists every commerce context; no present-tense for AMQP/catalog; `markdownlint` clean.
- [x] 3.1 Create `docs/GLOSSARY.md`: Usage, Domain terms, Events table (5 rows, producer+consumer), State vocabulary, Maintenance rule.
- [x] 3.2 Validate: event rows == ordered `Literal[...]` in `backend/app/shared/messaging/envelope.py`.

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `README.md` | Modified | Replaced 1-line placeholder with blueprint README |
| `PRD.md` | Created | Product Requirements Document with vision, personas, MVP scope, business rules, non-goals, and metrics |
| `docs/GLOSSARY.md` | Created | Canonical domain/event vocabulary, bounded contexts, event table, state transitions, maintenance rules |
| `openspec/changes/reconstruct-project-foundation/tasks.md` | Modified | Marked W0/W1/W2/W3 tasks complete |

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

## Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command and exact result | `python3 /tmp/opencode/validate_w3_glossary.py` → `GLOSSARY W3 validation passed.` |
| Runtime harness command/scenario and exact result | N/A — documentation-only W3 slice; no runtime boundary |
| Rollback boundary | `git rm docs/GLOSSARY.md` and `git checkout HEAD -- openspec/changes/reconstruct-project-foundation/tasks.md` reverts W3 without touching W2, W1, or excluded backend work |

## Validation Commands and Results

| Command | Result |
|---|---|
| `python3 /tmp/opencode/capture_baseline.py` | `Baseline captured: 259 paths -> $(git rev-parse --git-common-dir)/gentle-ai/sdd-baselines/reconstruct-project-foundation` |
| `python3 /tmp/opencode/compare_baseline.py` | `Baseline verified: 259 excluded paths unchanged.` |
| `python3 /tmp/opencode/validate_w1_readme.py` | `README W1 validation passed.` |
| `python3 /tmp/opencode/validate_w2_prd.py` | `PRD W2 validation passed.` |
| `python3 /tmp/opencode/validate_w3_glossary.py` | `GLOSSARY W3 validation passed.` |
| `git diff --stat README.md` | `README.md \| 62 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++-` |
| `wc -l PRD.md` | `80` |
| `wc -l docs/GLOSSARY.md` | `70` |
| `git diff --stat openspec/changes/reconstruct-project-foundation/tasks.md` | `4 ++--` (W2) + `2 +-` (W3) |

## Baseline Verification

- **Baseline directory**: `$(git rev-parse --git-common-dir)/gentle-ai/sdd-baselines/reconstruct-project-foundation/`
- **Excluded paths captured**: 259
- **Untracked**: 47; **Deleted**: 84; **Modified**: 15
- **Post-W1 comparison**: 0 status changes, 0 content changes among excluded paths
- **Post-W2 comparison**: 0 status changes, 0 content changes among excluded paths
- **Post-W3 comparison**: 0 status changes, 0 content changes among excluded paths
- **Conclusion**: No excluded path was added, removed, renamed, or had its status changed across W1, W2, or W3

## Deviations from Design

None — W3 implementation matches `design.md` and `proposal.md` for the GLOSSARY slice.

## Issues Found

- `markdownlint-cli` default rules (MD013 line-length 80, MD060 table-column-style) also fail on existing `README.md` and `PRD.md`. The W3 validator substitutes the same hygiene checks used for W1/W2, keeping style consistent across docs. A project-level `.markdownlint.json` should be added in the `integrate-development-environment` follow-up if strict markdownlint compliance is desired.

## Remaining Tasks

- [ ] 4a.1 Create `ARCHITECTURE.md` narrative
- [ ] 4a.2 Validate architecture narrative
- [ ] 4b.1 Extend `ARCHITECTURE.md` matrix + diagrams
- [ ] 4b.2 Validate architecture matrix
- [ ] 5.1 Create `docs/adr/README.md` + 5 ADRs
- [ ] 5.2 Validate ADRs
- [ ] 6.1 Create `DESIGN.md`
- [ ] 6.2 Validate `DESIGN.md`
- [ ] 7.1 Cross-link validation
- [ ] 7.2 Contract validation
- [ ] 7.3 Horizon + matrix validation
- [ ] 7.4 Quality + budget validation
- [ ] 7.5 Baseline closure

## Workload / PR Boundary

- **Mode**: feature-branch-chain
- **Current work unit**: W3 GLOSSARY
- **Branch**: `docs/w3-glossary` based on `docs/w2-prd`; PR will target `docs/w2-prd`
- **Boundary**: Starts after W2 PRD validation; ends with `docs/GLOSSARY.md` creation and W3 validation
- **Estimated review budget impact**: 70 changed lines, well within the 200-line W3 max and the 400-line gate

## Next Recommended

`sdd-verify` for W3, then proceed to W4a ARCHITECTURE narrative.
