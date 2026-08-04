"""Tests for the deterministic simulated payment approval policy.

Task 2.1: pinned SHA-256 fixtures (verified offline before writing this
file) plus N=1000 evaluation stability. The canonical bytes are UTF-8
``{order_id}|{amount-to-2-decimals}|{currency}`` and a payment is approved
iff the first digest byte is below the named threshold constant.
"""

from decimal import Decimal

from app.modules.payments.domain.policy import (
    APPROVAL_THRESHOLD,
    is_payment_approved,
    payment_digest_byte,
)

# (order_id, amount, currency, expected first digest byte, expected outcome)
VECTORS: list[tuple[str, Decimal, str, int, bool]] = [
    (
        "00000000-0000-0000-0000-000000000001",
        Decimal("19.99"),
        "USD",
        0x12,
        True,
    ),
    (
        "00000000-0000-0000-0000-000000000001",
        Decimal("0.00"),
        "USD",
        0xC9,
        False,
    ),
    (
        "00000000-0000-0000-0000-000000000001",
        Decimal("19.9"),
        "USD",
        0x09,
        True,
    ),
    (
        "00000000-0000-0000-0000-000000000001",
        Decimal("999.99"),
        "EUR",
        0x27,
        True,
    ),
    (
        "00000000-0000-0000-0000-000000000001",
        Decimal("0.01"),
        "GBP",
        0xD8,
        False,
    ),
    (
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
        Decimal("19.99"),
        "USD",
        0x34,
        True,
    ),
]


class TestPaymentDigestByte:
    def test_each_vector_matches_pinned_first_digest_byte(self) -> None:
        for order_id, amount, currency, expected_byte, _ in VECTORS:
            assert payment_digest_byte(order_id, amount, currency) == expected_byte

    def test_amount_is_canonicalized_to_two_decimals(self) -> None:
        assert payment_digest_byte(
            "00000000-0000-0000-0000-000000000001", Decimal("19.9"), "USD"
        ) == payment_digest_byte(
            "00000000-0000-0000-0000-000000000001", Decimal("19.90"), "USD"
        )

    def test_order_id_is_part_of_the_digest(self) -> None:
        v1 = payment_digest_byte(
            "00000000-0000-0000-0000-000000000001", Decimal("19.99"), "USD"
        )
        v6 = payment_digest_byte(
            "ffffffff-ffff-ffff-ffff-ffffffffffff", Decimal("19.99"), "USD"
        )
        assert v1 == 0x12
        assert v6 == 0x34
        assert v1 != v6


class TestIsPaymentApproved:
    def test_each_vector_maps_to_the_pinned_outcome(self) -> None:
        for order_id, amount, currency, _, approved in VECTORS:
            assert is_payment_approved(order_id, amount, currency) is approved

    def test_first_digest_byte_is_stable_across_1000_evaluations(self) -> None:
        for order_id, amount, currency, expected_byte, _ in VECTORS:
            seen = {
                payment_digest_byte(order_id, amount, currency) for _ in range(1000)
            }
            assert seen == {expected_byte}

    def test_outcome_is_stable_across_1000_evaluations(self) -> None:
        for order_id, amount, currency, _, approved in VECTORS:
            seen = {
                is_payment_approved(order_id, amount, currency) for _ in range(1000)
            }
            assert seen == {approved}

    def test_threshold_constant_is_named_and_equals_192(self) -> None:
        assert APPROVAL_THRESHOLD == 192
