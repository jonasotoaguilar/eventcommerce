<!-- ⚠️ READ BEFORE SUBMITTING
  Every PR must be linked to an issue that has the "status:approved" label.
  PRs without a linked approved issue will be automatically rejected by CI.
  See the issue templates and PR checks for the contribution workflow.
-->

## 🔗 Linked Issue

Closes #

<!-- Replace the # above with the issue number, e.g.: Closes #42 -->

---

## 🏷️ PR Type

What kind of change does this PR introduce?

- [ ] `type:bug` — Bug fix (non-breaking change that fixes an issue)
- [ ] `type:feature` — New feature (non-breaking change that adds functionality)
- [ ] `type:docs` — Documentation only
- [ ] `type:refactor` — Code refactoring (no functional changes)
- [ ] `type:chore` — Build, CI, or tooling changes
- [ ] `type:breaking-change` — Breaking change (fix or feature that changes existing behavior)

---

## 📝 Summary

<!-- Provide a clear and concise description of what this PR does and why. -->

---

## 📂 Changes

| File / Area | What Changed |
|-------------|-------------|
| `path/to/file` | Brief description |

---

## 🧪 Test Plan

**Setup + Lints + Tests**
```bash
cd backend
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check
uv run pytest
```

- [ ] Ruff check passes (`cd backend && uv run ruff check .`)
- [ ] Ruff format check passes (`cd backend && uv run ruff format --check .`)
- [ ] Pyrefly passes (`cd backend && uv run pyrefly check`)
- [ ] Pytest passes (`cd backend && uv run pytest`)
- [ ] Manually tested locally

<!-- Describe any additional manual testing steps if needed. -->

---

## 🤖 Automated Checks

The following checks run automatically on this PR:

| Check | Status | Description |
|-------|--------|-------------|
| Check Issue Reference | ⏳ | PR body must contain `Closes/Fixes/Resolves #N` |
| Check Issue Has `status:approved` | ⏳ | Linked issue must have been approved before work began |
| Check PR Has `type:*` Label | ⏳ | Exactly one `type:*` label must be applied |
| Ruff Check | ⏳ | `cd backend && uv run ruff check .` must pass |
| Ruff Format | ⏳ | `cd backend && uv run ruff format --check .` must pass |
| Pyrefly | ⏳ | `cd backend && uv run pyrefly check` must pass |
| Pytest | ⏳ | `cd backend && uv run pytest` must pass |

---

## ✅ Contributor Checklist

- [ ] PR is linked to an issue with `status:approved`
- [ ] I have added the appropriate `type:*` label to this PR
- [ ] Ruff check passes (`cd backend && uv run ruff check .`)
- [ ] Ruff format check passes (`cd backend && uv run ruff format --check .`)
- [ ] Pyrefly passes (`cd backend && uv run pyrefly check`)
- [ ] Pytest passes (`cd backend && uv run pytest`)
- [ ] I have updated documentation if necessary
- [ ] My commits follow [Conventional Commits](https://www.conventionalcommits.org/) format
- [ ] My commits do not include `Co-Authored-By` trailers

---

## 💬 Notes for Reviewers

<!-- Optional: anything you want reviewers to pay special attention to. -->
