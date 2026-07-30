```yaml
schema: gentle-ai.remediation-result/v1
status: complete
failed_evidence_revision: sha256:41013ae4cdbf0fe82cc98d4d67f2d4dccea9709d808bc0b333ff2a47eaafc5ab
focused_tests: passed
runtime_harness: passed
rollback_boundary: recorded
lineage_id: review-f4c2cbb5af104703b53c815da8dbde4a
generation: 2
fix_batch: 2
```

```json
{
  "schema": "gentle-ai.remediation-evidence/v1",
  "failed_evidence_revision": "sha256:41013ae4cdbf0fe82cc98d4d67f2d4dccea9709d808bc0b333ff2a47eaafc5ab",
  "lineage_id": "review-f4c2cbb5af104703b53c815da8dbde4a",
  "generation": 2,
  "fix_batch": 2,
  "red_command": "uv run pytest ../openspec/changes/reconstruct-project-foundation/verification/test_reconstruct_project_foundation.py",
  "red_cwd": "/home/jona/projects/eventcommerce-worktrees/w7-recovery/backend",
  "red_exit_code": 2,
  "red_result": "ModuleNotFoundError: No module named 'yaml'",
  "green_command": "uv run pytest -q ../openspec/changes/reconstruct-project-foundation/verification/test_reconstruct_project_foundation.py",
  "green_cwd": "/home/jona/projects/eventcommerce-worktrees/w7-recovery/backend",
  "green_exit_code": 0,
  "green_result": "85 passed in 0.08s; 12/12 spec scenarios",
  "refactor_command": "uv run ruff check ../openspec/changes/reconstruct-project-foundation/verification/test_reconstruct_project_foundation.py",
  "refactor_cwd": "/home/jona/projects/eventcommerce-worktrees/w7-recovery/backend",
  "refactor_exit_code": 0,
  "refactor_result": "All checks passed!"
}
```
