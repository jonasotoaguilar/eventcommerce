"""Tests for request payload canonicalization and SHA-256 hashing.

Slice 1 task 1.2 (RED): failing tests that pin the canonical form of a
checkout request — sorted object keys at every level, preserved item order,
Decimal amounts quantized to exactly two places — and the deterministic
64-char SHA-256 digest derived from the canonical bytes.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.shared.messaging.payload_hash import canonicalize_request, payload_hash

V1_CANONICAL = '{"amount":"19.90","currency":"USD"}'
V1_HASH = "d8bdf624944d08faae716dc98fa92242af7c4e455b5fe22943fc01e086e1d7e5"
V2_CANONICAL = (
    '{"amount":"0.00","currency":"USD","customer_id":"C1",'
    '"items":[{"product_id":"P1","quantity":2},{"product_id":"P2","quantity":1}]}'
)
V2_HASH = "07bcf25729c7ed0083c302d747fa44fb66d1cf13a9ae18a04d4382fe9f194088"


class TestCanonicalizeRequest:
    def test_sorts_top_level_keys(self) -> None:
        payload = {"currency": "USD", "amount": Decimal("19.9")}
        assert canonicalize_request(payload) == V1_CANONICAL

    def test_sorts_nested_item_keys(self) -> None:
        payload = {
            "amount": Decimal("0.00"),
            "currency": "USD",
            "customer_id": "C1",
            "items": [
                {"quantity": 2, "product_id": "P1"},
                {"quantity": 1, "product_id": "P2"},
            ],
        }
        assert canonicalize_request(payload) == V2_CANONICAL

    def test_preserves_item_order(self) -> None:
        first = {
            "items": [
                {"product_id": "P1", "quantity": 1},
                {"product_id": "P2", "quantity": 1},
            ]
        }
        swapped = {
            "items": [
                {"product_id": "P2", "quantity": 1},
                {"product_id": "P1", "quantity": 1},
            ]
        }
        assert canonicalize_request(first) != canonicalize_request(swapped)

    def test_quantizes_decimal_to_two_places(self) -> None:
        assert (
            canonicalize_request({"amount": Decimal("19.9"), "currency": "USD"})
            == '{"amount":"19.90","currency":"USD"}'
        )
        assert (
            canonicalize_request({"amount": Decimal("19.900"), "currency": "USD"})
            == '{"amount":"19.90","currency":"USD"}'
        )
        assert (
            canonicalize_request({"amount": Decimal("0"), "currency": "USD"})
            == '{"amount":"0.00","currency":"USD"}'
        )

    def test_deterministic_across_key_insertion_order(self) -> None:
        left = {"b": 1, "a": {"y": 2, "x": 3}}
        right = {"a": {"x": 3, "y": 2}, "b": 1}
        assert canonicalize_request(left) == canonicalize_request(right)
        assert canonicalize_request(left) == '{"a":{"x":3,"y":2},"b":1}'

    def test_raises_on_unsupported_value_type(self) -> None:
        with pytest.raises(TypeError):
            canonicalize_request({"amount": Decimal("1.00"), "when": object()})


class TestPayloadHash:
    def test_known_vector_amount_and_currency(self) -> None:
        assert payload_hash({"amount": Decimal("19.9"), "currency": "USD"}) == V1_HASH

    def test_known_vector_full_request(self) -> None:
        payload = {
            "amount": Decimal("0.00"),
            "currency": "USD",
            "customer_id": "C1",
            "items": [
                {"quantity": 2, "product_id": "P1"},
                {"quantity": 1, "product_id": "P2"},
            ],
        }
        assert payload_hash(payload) == V2_HASH

    def test_deterministic_across_evaluations(self) -> None:
        payload = {"currency": "EUR", "amount": Decimal("9.99")}
        assert payload_hash(payload) == payload_hash(payload)

    def test_differs_between_payloads(self) -> None:
        usd_one = {"amount": Decimal("1.00"), "currency": "USD"}
        assert payload_hash(usd_one) != payload_hash(
            {"amount": Decimal("1.01"), "currency": "USD"}
        )
        assert payload_hash(usd_one) != payload_hash(
            {"amount": Decimal("1.00"), "currency": "EUR"}
        )

    def test_returns_lowercase_hex_digest_of_64_chars(self) -> None:
        digest = payload_hash({"amount": Decimal("1.00"), "currency": "USD"})
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)
