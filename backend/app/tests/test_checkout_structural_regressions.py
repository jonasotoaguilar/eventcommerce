"""Structural regression tests for checkout end-to-end tasks 2.8, 4.1, 4.2.

Makes the previously static-verification-only TDD rows executable:

- 2.8: ADR 0005 records status "Accepted (current implementation)".
- 4.1: no application (non-test) Python source references the obsolete
  module path ``app.modules.orders.infrastructure.repositories.sqlalchemy_repository``.
- 4.2: the obsolete stub file ``backend/app/modules/orders/infrastructure/
  repositories/sqlalchemy_repository.py`` is absent while the live
  repository module remains present.

All paths resolve from ``__file__`` so the file also runs in disposable
worktree snapshots (pre-S2 ``6018493``, pre-S4 ``505c225``) without
environment or CWD assumptions.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ADR_0005_PATH = (
    REPO_ROOT / "docs" / "adr" / "0005-use-deterministic-simulated-payments.md"
)
APP_DIR = REPO_ROOT / "backend" / "app"
DEAD_STUB_PATH = (
    APP_DIR
    / "modules"
    / "orders"
    / "infrastructure"
    / "repositories"
    / "sqlalchemy_repository.py"
)
LIVE_REPO_PATH = (
    APP_DIR / "modules" / "orders" / "infrastructure" / "sqlalchemy_repository.py"
)

DEAD_MODULE_TOKEN = "repositories.sqlalchemy_repository"
LIVE_MODULE_TOKEN = "app.modules.orders.infrastructure.sqlalchemy_repository"

EXPECTED_ADR_STATUS = "Accepted (current implementation)"
MIN_SCANNED_FILES = 50


def _production_python_files() -> list[Path]:
    """All ``.py`` files under ``backend/app`` excluding test directories."""
    return sorted(
        py_file for py_file in APP_DIR.rglob("*.py") if "tests" not in py_file.parts
    )


def test_adr_0005_status_is_accepted_current_implementation() -> None:
    """Task 2.8: ADR 0005 records the accepted current implementation status."""
    text = ADR_0005_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    heading_indexes = [
        index for index, line in enumerate(lines) if line.strip() == "## Status"
    ]
    assert len(heading_indexes) == 1, (
        f"expected exactly one '## Status' heading in {ADR_0005_PATH}"
    )
    status = next(
        (line.strip() for line in lines[heading_indexes[0] + 1 :] if line.strip()),
        None,
    )
    assert status == EXPECTED_ADR_STATUS, (
        f"ADR 0005 status is {status!r}; expected {EXPECTED_ADR_STATUS!r}"
    )


def test_no_production_python_references_dead_module_path() -> None:
    """Task 4.1: nothing under the application imports the obsolete module."""
    offenders: list[Path] = []
    scanned = 0
    for py_file in _production_python_files():
        scanned += 1
        source = py_file.read_text(encoding="utf-8", errors="replace")
        if DEAD_MODULE_TOKEN in source:
            offenders.append(py_file)
    assert scanned >= MIN_SCANNED_FILES, (
        f"production scan covered only {scanned} files; "
        "repo path resolution is likely broken"
    )
    assert offenders == [], (
        f"obsolete module path {DEAD_MODULE_TOKEN!r} referenced by: "
        + ", ".join(str(py_file) for py_file in offenders)
    )


def test_positive_control_live_module_is_referenced() -> None:
    """The scanner can detect module-path references (anti-ghost guard)."""
    referencing = [
        py_file
        for py_file in _production_python_files()
        if LIVE_MODULE_TOKEN in py_file.read_text(encoding="utf-8", errors="replace")
    ]
    assert len(referencing) >= 1, (
        f"live module path {LIVE_MODULE_TOKEN!r} referenced by no "
        "production file; the 4.1 scan would not detect real references"
    )


def test_dead_stub_file_is_absent() -> None:
    """Task 4.2: the obsolete stub file was deleted and stays deleted."""
    assert not DEAD_STUB_PATH.exists(), f"obsolete stub still present: {DEAD_STUB_PATH}"


def test_live_repository_file_is_present() -> None:
    """Companion to the stub-absence test: the live module must survive."""
    assert LIVE_REPO_PATH.is_file(), f"live repository module missing: {LIVE_REPO_PATH}"
