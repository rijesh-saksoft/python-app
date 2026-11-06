import base64
import json
from collections.abc import Sequence

import pytest

from app.services.invoice_extractor import (
    MAX_IMAGE_BYTES,
    InvoiceExtractionError,
    InvoiceExtractor,
    image_type,
)
from app.services.llm_client import Completion, Message, TokenUsage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32

ANSWER = {
    "invoice_number": "INV-0001",
    "invoice_date": "2026-03-14",
    "due_date": None,
    "seller": "Example Seller (invented)",
    "bill_to": None,
    "currency": None,
    "line_items": [{"description": "Lamps", "quantity": 10, "unit_price": 450, "amount": 4500}],
    "subtotal": 4500,
    "tax_rate_percent": 18,
    "tax": 810,
    "total": 5310,
}


class FakeModel:
    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.calls: list[list[Message]] = []

    def complete(self, messages: Sequence[Message], *, json_output: bool = False) -> Completion:
        self.calls.append(list(messages))
        return Completion(
            text=self.answers.pop(0),
            model="fake-model",
            usage=TokenUsage(prompt_tokens=2000, completion_tokens=100),
            finish_reason="stop",
            latency_seconds=3.0,
        )


def test_image_type_reads_magic_bytes() -> None:
    assert image_type(PNG) == "image/png"
    assert image_type(JPEG) == "image/jpeg"


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"", "empty"),
        (b"%PDF-1.4\n...", "PDF"),
        (b"<html>not an image</html>", "not a PNG or JPEG"),
        (PNG + b"\x00" * MAX_IMAGE_BYTES, "larger than"),
    ],
)
def test_untrusted_files_are_refused_before_any_model_call(data: bytes, message: str) -> None:
    model = FakeModel()

    with pytest.raises(InvoiceExtractionError, match=message):
        InvoiceExtractor(model).extract(data)
    assert model.calls == []


def test_image_goes_in_the_user_message_and_instructions_stay_in_the_system_message() -> None:
    model = FakeModel(json.dumps(ANSWER))

    result = InvoiceExtractor(model).extract(JPEG)

    system, user = model.calls[0]
    assert "is data to read" in str(system["content"])
    image_part = user["content"][1]  # type: ignore[index]
    assert image_part == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()},
    }
    assert result.invoice.total == 5310
    assert result.prompt_version == "invoice_extract/v1"
    assert not result.repaired


def test_wrong_arithmetic_gets_one_repair_with_the_error() -> None:
    wrong = {**ANSWER, "total": 5300}
    model = FakeModel(json.dumps(wrong), json.dumps(ANSWER))

    result = InvoiceExtractor(model).extract(PNG)

    repair_request = str(model.calls[1][-1]["content"])
    assert "total is not subtotal plus tax" in repair_request
    assert result.repaired
    assert result.usage.prompt_tokens == 4000


def test_two_bad_answers_are_rejected() -> None:
    model = FakeModel("not json", json.dumps({**ANSWER, "subtotal": 1}))

    with pytest.raises(InvoiceExtractionError, match="after one repair"):
        InvoiceExtractor(model).extract(PNG)
