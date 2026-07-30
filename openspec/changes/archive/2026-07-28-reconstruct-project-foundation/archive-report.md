# Archive Report: Reconstruct Project Foundation

**Outcome**: Archived at `openspec/changes/archive/2026-07-28-reconstruct-project-foundation/`. SDD cycle complete. Spec synced to main as `openspec/specs/project-foundation-docs/spec.md`.

## Quick path

- Specs merged to main (new domain, 9 requirements, 12 scenarios)
- Change folder moved to archive with ISO date prefix
- 22/22 tasks complete, 9/9 requirements, 12/12 scenarios, 85 spec-verifier tests pass
- Review gate: `allow` (native lineage `review-0ee47df4966e4840b5e6271506db1615`)
- No `CRITICAL` issues in verify-report; one non-blocking `WARNING`

## What shipped

| Area | Action | Evidence |
|------|--------|----------|
| Root docs | Created `README.md`, `PRD.md`, `ARCHITECTURE.md`, `DESIGN.md` | verify-report S1, S2, S3, S6 PASS |
| Glossary | Created `docs/GLOSSARY.md` with 7 governed events (4 Now + 3 MVP Target) | S4, S8 PASS |
| ADRs | Seeded 5 ADRs (`0001`–`0005`) + `docs/adr/README.md` index | S8 PASS |
| Architecture status matrix | Now / MVP Target / Future honesty enforced | S3 PASS |
| Source hierarchy | Published Git Now binding; dirty refactor = MVP Target only | S4, S5 PASS |
| Excluded paths | Preserved via captured pre-apply baseline | S12 PASS |
| Review budget | 7 chained PRs (W0–W7) under 400-line gate each | S11 PASS |

## Spec sync

| Domain | Action | Details |
|--------|--------|---------|
| `project-foundation-docs` | Created | Delta was pure `ADDED Requirements`; no prior main spec existed. 9 requirements (R1–R9), 12 scenarios (S1–S12) copied to main with `## ADDED Requirements` header normalized to `## Requirements`. |

## Final verification state

Per the orchestrator's launch prompt (rank 3) and the native review gate (rank 1), the runtime is complete and passed. Per the verify-report (rank 4, intermediate snapshot), all 12 scenarios passed at verification time.

| Check | Command | Result |
|-------|---------|--------|
| Spec scenario suite | `uv run pytest ../openspec/changes/reconstruct-project-foundation/verification/test_reconstruct_project_foundation.py` | 85/85 passed, 12/12 scenarios, exit 0 |
| Full backend suite | `uv run pytest` | 89 passed (85 spec + 4 backend), exit 0 |
| Linter | `uv run ruff check` | 0 errors, exit 0 |
| Type checker | `uv run pyrefly check` | 0 errors, exit 0 |
| Build / compile | `uv run python -m compileall -q app/modules/orders/domain app/modules/inventory/domain app/modules/payments/domain app/modules/notifications/domain` | 0 errors, exit 0 |
| reviewGate | native | `allow` — explicit bound compact authority exactly matches the current repository |

Coverage was skipped — `pytest-cov` is not declared in `backend/pyproject.toml`.

## Review trail (native)

| Item | Value |
|------|-------|
| Native successor lineage | `review-0ee47df4966e4840b5e6271506db1615` |
| Authority revision | `sha256:5400694bf8895c141c4b30a2836ad2a3fcfdd39585551a511ebe2b2fb66f75c3` |
| SDD binding revision | `sha256:9e3d67237170482016f0321257e08fdccade76e97618a5295373ecc1809dad01` |
| Runtime attempt revision | `sha256:4a9836d85e2b628cac8959647baf0e422eeaecbe2e5b06036e6f483bb29705c3` |
| Evidence revision | `sha256:9bf531f175929b773c4ed679139ad05e4d8a6c7915e6fd63135173164be15157` |
| Remediation lineage | `review-f4c2cbb5af104703b53c815da8dbde4a`, gen 2, fix_batch 2 — `complete`, focused_tests `passed`, runtime_harness `passed`, rollback_boundary `recorded` |

## TDD evidence (per verify-report, intermediate snapshot)

| Cycle | Command | Result |
|-------|---------|--------|
| RED | `uv run pytest ...` | exit 2, `ModuleNotFoundError: No module named 'yaml'` |
| GREEN | `uv run pytest -q ...` | exit 0, 85 passed in 0.08s; 12/12 spec scenarios |
| REFACTOR | `uv run ruff check ...` | exit 0, `All checks passed!` |

## Known characteristics

- **PyYAML dependency**: `backend/pyproject.toml` had PyYAML added for the spec-verifier test runner. The verify-report acknowledges this as the sole permitted excluded-path change, and the S12 baseline integrity was preserved. Listed here for transparency — not a CRITICAL issue.
- **Non-blocking WARNING** (from verify-report): The S2, S4–S12 assertions could be strengthened with deeper checks (exact ownership boundaries, anchor resolution, doc-slice diff history, baseline content/status equality). The current assertions are sufficient for gate-passing but not exhaustive.
- **Suggestion** (from verify-report): Add `pytest-cov` to `backend/pyproject.toml` dev deps for coverage tracking on future spec-verifier runs.
- **PR topology**: 7 chained PRs (W0–W7) under the 400-line review budget via `feature-branch-chain` strategy; only the tracker merges to main.

## Archive contents

- `proposal.md` — intent, scope, capabilities, approach, affected areas, risks, delivery forecast, rollback, dependencies, success criteria, staged follow-up program
- `specs/project-foundation-docs/spec.md` — delta spec (9 requirements, 12 scenarios)
- `design.md` — technical approach, architecture decisions, document blueprints, interfaces/contracts, diagrams, testing strategy, work units, spec traceability
- `tasks.md` — 22/22 tasks complete (W0–W7, all `[x]`)
- `apply-progress.md` — remediation gen-2 evidence (RED/GREEN/REFACTOR)
- `verify-report.md` — PASS, 9/9, 12/12, 0 blockers, 0 critical findings
- `exploration.md` — historical snapshot against dirty refactor tree (not Now evidence)
- `verification/test_reconstruct_project_foundation.py` — 85 parametrized assertions, 12 scenarios

## Source of truth

- `openspec/specs/project-foundation-docs/spec.md` — 9 requirements, 12 scenarios, all `ADDED` (new domain)

## Final-state authority notes

- The verify-report's "all 12 scenarios pass" claim is from the verification-time snapshot; the orchestrator's launch prompt confirms runtime passed with 85 spec-verifier + 4 backend tests, Ruff, Pyrefly, and compileall all green.
- The `apply-progress.md` is a `remediation-result/v1` envelope (gen 2, fix_batch 2) that resolved the PyYAML missing-module failure; it is the most recent task-side artifact and confirms completion.

## Next step

SDD cycle complete. Ready for the next change. The staged follow-up program in `proposal.md` (changes 1–11) is unblocked by this foundation.
