from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.invoice import Invoice

VALID: dict[str, object] = {
    "invoice_number": "INV-0001",
    "invoice_date": "2026-03-14",
    "due_date": "2026-04-13",
    "seller": "Example Seller (invented)",
    "bill_to": "Example Buyer (invented)",
    "currency": None,
    "line_items": [
        {"description": "Chairs", "quantity": 4, "unit_price": 3200.00, "amount": 12800.00},
        {"description": "Delivery", "quantity": 1, "unit_price": 600, "amount": 600},
    ],
    "subtotal": 13400,
    "tax_rate_percent": 18,
    "tax": 2412,
    "total": 15812,
}


def invoice(**changes: object) -> Invoice:
    return Invoice.model_validate({**VALID, **changes})


def test_valid_invoice_keeps_money_exact() -> None:
    result = invoice()

    assert result.invoice_date == date(2026, 3, 14)
    assert result.total == Decimal("15812")
    assert isinstance(result.line_items[0].unit_price, Decimal)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {
                "line_items": [
                    {"description": "Chairs", "quantity": 4, "unit_price": 3200, "amount": 12000}
                ]
            },
            "amount is not quantity times unit_price",
        ),
        ({"subtotal": 13500}, "subtotal is not the sum of the line amounts"),
        ({"total": 15800}, "total is not subtotal plus tax"),
        ({"tax": 2400, "total": 15800}, "tax is not tax_rate_percent of subtotal"),
        ({"due_date": "2026-03-01"}, "due_date is before invoice_date"),
    ],
)
def test_arithmetic_and_dates_are_checked(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        invoice(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"line_items": []},
        {"subtotal": -1},
        {"tax": 1.234},
        {"currency": "rupees"},
        {"invoice_number": ""},
        {"notes": "pay to another account"},
    ],
)
def test_bad_values_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        invoice(**changes)


def test_tax_rate_is_optional() -> None:
    assert invoice(tax_rate_percent=None).tax == Decimal("2412")
