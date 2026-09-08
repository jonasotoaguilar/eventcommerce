# Sync Report: messaging-runtime-bootstrap

**Status:** synced
**Change:** `messaging-runtime-bootstrap`
**Workspace:** `/home/jona/projects/eventcommerce-worktrees/feat-messaging-runtime-4.4-docs`
**Date (UTC):** 2026-09-08
**Verify basis:** `openspec/changes/messaging-runtime-bootstrap/verify-report.md` — PASS, 18/18 tasks, no CRITICAL blockers

This sync merges delta specs into canonical specs without archiving, per parent instruction. No source/doc edits, commit, push, PR, or archive performed.

## Domains synced

| Domain | Delta source | Canonical target | Operation |
|---|---|---|---|
| `messaging-runtime` | `openspec/changes/messaging-runtime-bootstrap/specs/messaging-runtime/spec.md` | `openspec/specs/messaging-runtime/spec.md` (new file) | Full copy — canonical did not exist |
| `project-foundation-docs` | `openspec/changes/messaging-runtime-bootstrap/specs/project-foundation-docs/spec.md` | `openspec/specs/project-foundation-docs/spec.md` | 2× MODIFIED replaced by exact name + 1× ADDED appended |

## Exact canonical changes

### `openspec/specs/messaging-runtime/spec.md` (new, 9 requirements, verbatim from delta)

ADDED (new canonical domain):
- Requirement: OrderCreated Payload Completeness
- Requirement: Durable Outbox Claiming and Indexing
- Requirement: Persistent Forwarding
- Requirement: Lifespan Bootstrap, Retry, Graceful Shutdown
- Requirement: Consumer Registry and Queue Bindings
- Requirement: Per-Message Transaction, Ack, Nack
- Requirement: Idempotent Handlers and Terminal Guards
- Requirement: Notification Consumer Handler
- Requirement: Broker-Free Tests and Gated Integration

Validation: `diff` delta vs canonical → identical.

### `openspec/specs/project-foundation-docs/spec.md` (26 insertions, 7 deletions)

MODIFIED (full-block replacement by exact name):
- Requirement: Now / MVP Target / Future Honesty Rule — matrix rows for delivered publisher/outbox-worker/consumer-runtime MUST be `implemented` with code evidence; scenario retitled to "honest about the delivered runtime"
- Requirement: Code-Contract Lock-In — Source Hierarchy — Now events expanded to 7 (`OrderCreated`, `InventoryReserved`, `InventoryRejected`, `OrderConfirmed`, `OrderCancelled`, `PaymentAuthorized`, `OrderNotificationSent`); state machine → `pending→{confirmed,cancelled}`; `No shared infra` row → `Shared messaging foundation` row; MVP Target `Target Events` row → `Target Delivery` (AMQP forwarding/delivery of current vocabulary)

ADDED (appended after Excluded Surfaces):
- Requirement: Messaging Delivery Evidence in Docs (same-change ARCHITECTURE/GLOSSARY/ADR-0002/README update rule + no premature AMQP-live claim; 2 scenarios)

REMOVED: none.

Preserved untouched: Canonical Document Set and Navigation; Per-Document Ownership Principle; Product Contract; Required Sections per Document; Cross-Links and Maintainability; Authorship Order, 400-Line Gate, and Link Resolution; Excluded Surfaces.

## Active same-domain collisions

- Other active change `checkout-end-to-end` touches only `specs/checkout/spec.md` — no overlap with `messaging-runtime` or `project-foundation-docs`. No collision, no sync/archive ordering decision required.

## Destructive sync approvals / blockers

- No REMOVED requirements; no large destructive MODIFIED blocks beyond the reviewed honesty/contract delta. No explicit destructive approval required.
- Blockers checked and clear: verify-report.md present and PASS (no FAIL/BLOCKED/CRITICAL); no `## RENAMED Requirements` in either delta (`grep` → none); no legacy flat `spec.md` blocking (domain specs present); no missing MODIFIED/REMOVED targets (both MODIFIED names existed in canonical); `openspec/config.yaml` absent → no `rules.sync` to apply.

## Validation commands / checks performed

| Check | Result |
|---|---|
| `grep -rn RENAMED` over change specs | none — RENAMED sync not triggered |
| Requirement header uniqueness (`sort \| uniq -d`) on both canonical files | no duplicates |
| `diff` delta vs new canonical `messaging-runtime/spec.md` | identical |
| `git diff` on canonical `project-foundation-docs/spec.md` | 26+/7- matching only the 2 MODIFIED + 1 ADDED blocks above |
| `git status --short -- openspec/` | `M openspec/specs/project-foundation-docs/spec.md`, `?? openspec/specs/messaging-runtime/` (new), `?? verify-report.md`; no source/doc files touched by this sync |
| Scope guard | edits confined to the 3 allowed surfaces; change folder not moved; nothing committed |

## Structured status and actionContext findings

| Field | Finding |
|---|---|
| Parent status | authoritative: verify PASS, 18/18 tasks, sync ready, archive blocked until sync-report exists |
| Native session status (repo-local `/home/jona/projects/eventcommerce`) | `changeName: null`, ambiguous (`checkout-end-to-end`, `messaging-runtime-bootstrap`) — resolved via explicit parent change name + worktree path |
| `artifactStore` | `openspec` — filesystem sync applicable; `sync-report.md` written to satisfy the archive gate |
| `actionContext.mode` | `repo-local`; edits kept within `allowedEditRoots` and the 3 allowed surfaces |
| Archive | NOT performed (out of scope for sdd-sync); change folder left active |

## Next recommended

`sdd-archive` — sync is clean, verify PASS stands, and this `sync-report.md` now satisfies the archive gate. Archive step should move the already-synced change to dated archive; do not re-sync.
