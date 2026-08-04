"""Tests for the checkout request/response contract schemas.

Task 3.4 (RED): CheckoutRequest validation must reject ``quantity=0``,
empty ``items``, invalid currency (syntactic ISO 4217: exactly three
uppercase ASCII letters, no catalog existence check), ``amount`` with more
than two decimals, and missing fields, while a fully valid request passes
through (the 201-class pass-through at schema level).

Task 3.13 (GREEN): pins every approved contract constraint from
``openspec/changes/checkout-end-to-end/design.md`` — customer/product IDs
1-128 chars, 1-100 unique items, quantity 1-10,000, amount Decimal
0-999,999,999.99 with at most two decimals, currency normalized then
validated as three uppercase ASCII letters, optional visible-ASCII
Idempotency-Key 1-128 chars, and CheckoutResponse with order_id/status plus
nullable cancel_reason/payment_status.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.checkout.api.schemas import CheckoutRequest, CheckoutResponse

VALID_PAYLOAD: dict = {
    "customer_id": "cust-123",
    "items": [
        {"product_id": "P1", "quantity": 2},
        {"product_id": "P2", "quantity": 1},
    ],
    "amount": "19.99",
    "currency": "USD",
    "idempotency_key": "checkout-key-123",
}


def valid_request(**overrides: object) -> dict:
    payload = dict(VALID_PAYLOAD)
    payload.update(overrides)
    return payload


class TestValidRequestPassThrough:
    """Scenario: a fully valid request proceeds (201-class pass-through)."""

    def test_full_valid_request_parses(self) -> None:
        request = CheckoutRequest.model_validate(VALID_PAYLOAD)
        assert request.customer_id == "cust-123"
        assert [(i.product_id, i.quantity) for i in request.items] == [
            ("P1", 2),
            ("P2", 1),
        ]
        assert request.amount == Decimal("19.99")
        assert request.currency == "USD"
        assert request.idempotency_key == "checkout-key-123"

    def test_idempotency_key_is_optional(self) -> None:
        request = CheckoutRequest.model_validate(valid_request(idempotency_key=None))
        assert request.idempotency_key is None

    def test_currency_is_normalized_then_validated(self) -> None:
        request = CheckoutRequest.model_validate(valid_request(currency="usd"))
        assert request.currency == "USD"

    def test_boundary_values_are_accepted(self) -> None:
        request = CheckoutRequest.model_validate(
            valid_request(
                customer_id="c" * 128,
                items=[{"product_id": f"p{i}", "quantity": 1} for i in range(100)],
                amount="999999999.99",
                currency="EUR",
                idempotency_key="k" * 128,
            )
        )
        assert request.customer_id == "c" * 128
        assert len(request.items) == 100
        assert request.amount == Decimal("999999999.99")

    def test_quantity_and_amount_lower_bounds_are_accepted(self) -> None:
        request = CheckoutRequest.model_validate(
            valid_request(
                items=[{"product_id": "P1", "quantity": 1}],
                amount="0",
            )
        )
        assert request.items[0].quantity == 1
        assert request.amount == Decimal("0")


class TestQuantityValidation:
    """Scenario: invalid quantity or empty items rejected."""

    @pytest.mark.parametrize("quantity", [0, -1, 10_001])
    def test_quantity_out_of_range_rejected(self, quantity: int) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(
                valid_request(items=[{"product_id": "P1", "quantity": quantity}])
            )

    def test_empty_items_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(items=[]))

    def test_item_missing_quantity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(items=[{"product_id": "P1"}]))


class TestCurrencyValidation:
    """Syntactic ISO 4217: exactly three uppercase ASCII letters."""

    @pytest.mark.parametrize("currency", ["US", "US1", "USAA", "", "USD!", "US D"])
    def test_invalid_currency_rejected(self, currency: str) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(currency=currency))

    def test_missing_currency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(currency=None))


class TestAmountValidation:
    """Decimal 0-999,999,999.99 with at most two decimal places."""

    @pytest.mark.parametrize("amount", ["19.999", "0.001", "1.230"])
    def test_amount_with_more_than_two_decimals_rejected(self, amount: str) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(amount=amount))

    def test_negative_amount_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(amount="-1"))

    def test_amount_above_max_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(amount="1000000000.00"))


class TestMissingFields:
    """Any required field absent yields a validation error."""

    @pytest.mark.parametrize("field", ["customer_id", "items", "amount", "currency"])
    def test_missing_required_field_rejected(self, field: str) -> None:
        payload = valid_request()
        del payload[field]
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(payload)


class TestItemUniquenessAndBounds:
    """1-100 unique items; product_id 1-128 chars."""

    def test_duplicate_product_ids_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(
                valid_request(
                    items=[
                        {"product_id": "P1", "quantity": 1},
                        {"product_id": "P1", "quantity": 2},
                    ]
                )
            )

    def test_more_than_100_items_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(
                valid_request(
                    items=[{"product_id": f"p{i}", "quantity": 1} for i in range(101)]
                )
            )

    def test_empty_product_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(
                valid_request(items=[{"product_id": "", "quantity": 1}])
            )

    def test_product_id_longer_than_128_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(
                valid_request(items=[{"product_id": "p" * 129, "quantity": 1}])
            )


class TestCustomerIdLength:
    """customer_id 1-128 characters."""

    def test_empty_customer_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(customer_id=""))

    def test_customer_id_longer_than_128_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(customer_id="c" * 129))


class TestIdempotencyKeyConstraints:
    """Optional Idempotency-Key, 1-128 visible ASCII characters."""

    @pytest.mark.parametrize(
        "key",
        [
            "",
            "key with space",
            "control\x07char",
            "k" * 129,
            "accént",
        ],
    )
    def test_invalid_idempotency_key_rejected(self, key: str) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(valid_request(idempotency_key=key))


class TestCheckoutResponse:
    """Response carries order_id/status and nullable cancel/payment fields."""

    def test_response_with_optional_fields_nullable(self) -> None:
        response = CheckoutResponse(
            order_id="ord-1",
            status="confirmed",
            cancel_reason=None,
            payment_status=None,
        )
        assert response.order_id == "ord-1"
        assert response.status == "confirmed"
        assert response.cancel_reason is None
        assert response.payment_status is None

    def test_response_with_all_fields_set(self) -> None:
        response = CheckoutResponse(
            order_id="ord-2",
            status="cancelled",
            cancel_reason="insufficient_stock",
            payment_status="declined",
        )
        assert response.cancel_reason == "insufficient_stock"
        assert response.payment_status == "declined"

    def test_response_requires_order_id_and_status(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutResponse.model_validate({"order_id": "ord-3"})
