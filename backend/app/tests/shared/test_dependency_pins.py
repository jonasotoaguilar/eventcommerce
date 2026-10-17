"""Regression pins for the dependency advisories remediated in W1.

A lock file is regenerated often; these tests fail if a flagged release comes
back through a resolution change rather than through a deliberate decision.
Each pin is a minimum, so a later legitimate upgrade keeps passing.
"""

import re
from pathlib import Path

_LOCK = Path(__file__).resolve().parents[3] / "uv.lock"

_MINIMUM_VERSIONS = {
    "pyjwt": (2, 15, 1),
    "mako": (1, 4, 3),
    "multidict": (7, 1, 0),
}


def _resolved_versions(lock_text: str) -> dict[str, tuple[int, ...]]:
    resolved: dict[str, tuple[int, ...]] = {}
    for name, raw in re.findall(
        r'^name = "([^"]+)"\nversion = "([^"]+)"', lock_text, re.MULTILINE
    ):
        parts = tuple(int(part) for part in raw.split(".") if part.isdigit())
        resolved[name] = parts
    return resolved


def test_flagged_backend_dependencies_resolve_at_or_above_their_fixed_release() -> None:
    resolved = _resolved_versions(_LOCK.read_text())

    for name, minimum in _MINIMUM_VERSIONS.items():
        assert name in resolved, f"{name} is no longer locked"
        assert resolved[name] >= minimum, (
            f"{name} resolved to {'.'.join(map(str, resolved[name]))}, "
            f"below the fixed release {'.'.join(map(str, minimum))}"
        )
