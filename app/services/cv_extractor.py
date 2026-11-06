"""Extract a CandidateProfile from CV text with a language model (Playbook AI-04, AI-05).

The CV is untrusted. It goes only in the user message, between <cv> markers it cannot
close, and never into the instructions. The answer is validated with one repair retry.
"""

import re
from dataclasses import dataclass

from app.models.cv import CandidateProfile
from app.services.llm_client import Message, TokenUsage
from app.services.prompts import load_prompt
from app.services.structured_output import (
    ChatModel,
    StructuredOutputError,
    complete_structured,
)

MAX_CV_CHARS = 20_000
_MARKER = re.compile(r"</?cv>", re.IGNORECASE)


class CvExtractionError(Exception):
    """The CV cannot be extracted: bad input, or no valid answer after one repair."""


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    profile: CandidateProfile
    prompt_version: str
    model: str
    repaired: bool
    usage: TokenUsage
    latency_seconds: float


class CvExtractor:
    def __init__(self, model: ChatModel, prompt_version: str = "v1") -> None:
        self._model = model
        self._prompt = load_prompt("cv_extract", prompt_version)

    def extract(self, cv_text: str) -> ExtractionResult:
        if not cv_text.strip():
            raise CvExtractionError("the CV is empty")
        if len(cv_text) > MAX_CV_CHARS:
            raise CvExtractionError(f"the CV is longer than {MAX_CV_CHARS} characters")

        messages: list[Message] = [
            {"role": "system", "content": self._prompt.text},
            {"role": "user", "content": _wrap(cv_text)},
        ]
        try:
            answer = complete_structured(self._model, messages, CandidateProfile)
        except StructuredOutputError as exc:
            raise CvExtractionError(str(exc)) from exc
        return ExtractionResult(
            profile=answer.value,
            prompt_version=self._prompt.id,
            model=answer.model,
            repaired=answer.repaired,
            usage=answer.usage,
            latency_seconds=answer.latency_seconds,
        )


def _wrap(cv_text: str) -> str:
    """Put the CV between markers, after removing any markers inside it."""
    return f"<cv>\n{_MARKER.sub('', cv_text).strip()}\n</cv>"
