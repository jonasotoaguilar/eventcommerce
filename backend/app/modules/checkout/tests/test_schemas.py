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
        assert request.items is not None
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
        assert request.items is not None
        assert len(request.items) == 100
        assert request.amount == Decimal("999999999.99")

    def test_quantity_and_amount_lower_bounds_are_accepted(self) -> None:
        request = CheckoutRequest.model_validate(
            valid_request(
                items=[{"product_id": "P1", "quantity": 1}],
                amount="0",
            )
        )
        assert request.items is not None
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

    @pytest.mark.parametrize("field", ["items", "amount", "currency"])
    def test_missing_required_field_rejected(self, field: str) -> None:
        payload = valid_request()
        del payload[field]
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(payload)

    def test_missing_customer_id_validates_to_none(self) -> None:
        payload = valid_request()
        del payload["customer_id"]
        assert CheckoutRequest.model_validate(payload).customer_id is None


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


class TestCartIdShape:
    """U3: cart_id alone is valid; mixing with inline fields is a 422."""

    def test_cart_id_alone_validates(self) -> None:
        request = CheckoutRequest.model_validate(
            {"cart_id": "11111111-1111-1111-1111-111111111111"}
        )
        assert str(request.cart_id) == "11111111-1111-1111-1111-111111111111"
        assert request.items is None
        assert request.amount is None
        assert request.currency is None

    def test_cart_id_with_compat_keys_validates(self) -> None:
        request = CheckoutRequest.model_validate(
            {
                "cart_id": "11111111-1111-1111-1111-111111111111",
                "customer_id": "compat-id",
                "idempotency_key": "cart-key-1",
            }
        )
        assert request.customer_id == "compat-id"
        assert request.idempotency_key == "cart-key-1"

    @pytest.mark.parametrize("field", ["items", "amount", "currency"])
    def test_cart_id_mixed_with_inline_field_rejected(self, field: str) -> None:
        payload: dict = {"cart_id": "11111111-1111-1111-1111-111111111111"}
        payload.update(valid_request())
        # valid_request carries all inline fields; keep only the mixed one.
        for other in ("items", "amount", "currency"):
            if other != field:
                del payload[other]
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(payload)

    def test_cart_id_mixed_with_all_inline_fields_rejected(self) -> None:
        payload = valid_request()
        payload["cart_id"] = "11111111-1111-1111-1111-111111111111"
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(payload)

    @pytest.mark.parametrize("field", ["items", "amount", "currency"])
    def test_inline_missing_field_without_cart_rejected(self, field: str) -> None:
        payload = valid_request()
        del payload[field]
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate(payload)

    def test_fully_empty_request_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate({})

    def test_invalid_cart_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CheckoutRequest.model_validate({"cart_id": "not-a-uuid"})
