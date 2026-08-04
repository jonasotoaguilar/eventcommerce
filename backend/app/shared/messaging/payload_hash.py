"""Canonical request payload serialization and SHA-256 hashing.

The idempotency claim stores a payload fingerprint so reusing an
``Idempotency-Key`` with a different request body can be detected. Two
requests are "identical" when their canonical JSON bytes are equal:

* object keys are sorted at every nesting level (``sort_keys``),
* array order is preserved (item order is significant),
* ``Decimal`` amounts are quantized to exactly two decimal places and
  serialized as strings, so ``19.9``, ``19.90``, and ``19.900`` collide.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Mapping

_TWO_PLACES = Decimal("0.01")


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value.quantize(_TWO_PLACES))
    raise TypeError(f"cannot canonicalize {type(value).__name__} value")


def canonicalize_request(payload: Mapping[str, Any]) -> str:
    """Compact, deterministic JSON for one checkout request payload."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def payload_hash(payload: Mapping[str, Any]) -> str:
    """SHA-256 hex digest (64 chars) of the canonical request bytes."""
    canonical = canonicalize_request(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
