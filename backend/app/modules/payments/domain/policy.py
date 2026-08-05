"""Deterministic simulated payment approval policy (ADR 0005 P2).

A payment is approved if and only if the first byte of
``sha256("{order_id}|{amount}|{currency}")`` is below a fixed threshold.
The canonical bytes are UTF-8 ``lowercase-hyphenated-uuid|amount-to-2-
decimals|UPPERCASE-CURRENCY``; identical input always yields the same
result, so tests and demos are reproducible.
"""

import hashlib
from decimal import Decimal

APPROVAL_THRESHOLD = 192


def payment_digest_byte(order_id: str, amount: Decimal, currency: str) -> int:
    """First SHA-256 digest byte over the UTF-8 canonical payment bytes."""
    canonical = f"{order_id}|{amount:.2f}|{currency}".encode("utf-8")
    return hashlib.sha256(canonical).digest()[0]


def is_payment_approved(order_id: str, amount: Decimal, currency: str) -> bool:
    """True when the payment policy approves the authorization."""
    return payment_digest_byte(order_id, amount, currency) < APPROVAL_THRESHOLD
