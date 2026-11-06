"""The shape an invoice is extracted into. Model output is untrusted, so the schema checks
the arithmetic: a misread digit shows up as a sum that does not add up. Money is Decimal,
never float."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
_CENT = Decimal("0.01")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class LineItem(_Strict):
    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit_price: Money
    amount: Money

    @model_validator(mode="after")
    def _amount_matches(self) -> Self:
        if (self.quantity * self.unit_price).quantize(_CENT) != self.amount:
            raise ValueError("amount is not quantity times unit_price")
        return self


class Invoice(_Strict):
    invoice_number: str = Field(min_length=1)
    invoice_date: date
    due_date: date | None = None
    seller: str = Field(min_length=1)
    bill_to: str | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")  # ISO code, if shown
    line_items: list[LineItem] = Field(min_length=1, max_length=200)
    subtotal: Money
    tax_rate_percent: Decimal | None = Field(default=None, ge=0, le=100)
    tax: Money
    total: Money

    @model_validator(mode="after")
    def _adds_up(self) -> Self:
        if sum(item.amount for item in self.line_items) != self.subtotal:
            raise ValueError("subtotal is not the sum of the line amounts")
        if self.tax_rate_percent is not None:
            expected_tax = (self.subtotal * self.tax_rate_percent / 100).quantize(_CENT)
            if expected_tax != self.tax:
                raise ValueError("tax is not tax_rate_percent of subtotal")
        if self.subtotal + self.tax != self.total:
            raise ValueError("total is not subtotal plus tax")
        if self.due_date is not None and self.due_date < self.invoice_date:
            raise ValueError("due_date is before invoice_date")
        return self
