"""Extract an Invoice from an invoice image with a vision model (Playbook AI-04, AI-05).

The file is untrusted. Its type is decided by its first bytes, not its name, and only PNG
and JPEG are accepted, so no PDF or other parser runs inside the service. A PDF page must be
converted to an image first. The image goes only in the user message; the instructions say
that text inside it is data.
"""

import base64
from dataclasses import dataclass

from app.models.invoice import Invoice
from app.services.llm_client import Message, TokenUsage
from app.services.prompts import load_prompt
from app.services.structured_output import (
    ChatModel,
    StructuredOutputError,
    complete_structured,
)

MAX_IMAGE_BYTES = 5_000_000
_SIGNATURES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg"}


class InvoiceExtractionError(Exception):
    """The invoice cannot be extracted: bad file, or no valid answer after one repair."""


@dataclass(frozen=True, slots=True)
class InvoiceResult:
    invoice: Invoice
    prompt_version: str
    model: str
    repaired: bool
    usage: TokenUsage
    latency_seconds: float


def image_type(data: bytes) -> str:
    """Return the media type of an accepted image, judged by its first bytes."""
    if not data:
        raise InvoiceExtractionError("the file is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise InvoiceExtractionError(f"the file is larger than {MAX_IMAGE_BYTES} bytes")
    if data.startswith(b"%PDF-"):
        raise InvoiceExtractionError("the file is a PDF; convert the page to PNG first")
    for signature, media_type in _SIGNATURES.items():
        if data.startswith(signature):
            return media_type
    raise InvoiceExtractionError("the file is not a PNG or JPEG image")


class InvoiceExtractor:
    def __init__(self, model: ChatModel, prompt_version: str = "v1") -> None:
        self._model = model
        self._prompt = load_prompt("invoice_extract", prompt_version)

    def extract(self, image: bytes) -> InvoiceResult:
        media_type = image_type(image)
        data_url = f"data:{media_type};base64,{base64.b64encode(image).decode()}"
        messages: list[Message] = [
            {"role": "system", "content": self._prompt.text},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "The invoice image:"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
        try:
            answer = complete_structured(self._model, messages, Invoice)
        except StructuredOutputError as exc:
            raise InvoiceExtractionError(str(exc)) from exc
        return InvoiceResult(
            invoice=answer.value,
            prompt_version=self._prompt.id,
            model=answer.model,
            repaired=answer.repaired,
            usage=answer.usage,
            latency_seconds=answer.latency_seconds,
        )
