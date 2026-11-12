"""Get a validated Pydantic object out of a language model (Playbook AI-05).

The model's answer is untrusted: it is parsed and validated, given one repair retry with
the exact errors, then rejected.
"""

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ValidationError

from app.services.llm_client import Completion, Message, TokenUsage
from app.services.prompts import load_prompt

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class ChatModel(Protocol):
    def complete(
        self, messages: Sequence[Message], *, json_output: bool = False
    ) -> Completion: ...


class StructuredOutputError(Exception):
    """The model gave no valid answer after one repair."""


@dataclass(frozen=True, slots=True)
class StructuredAnswer[T: BaseModel]:
    value: T
    model: str
    repaired: bool
    usage: TokenUsage
    latency_seconds: float


def complete_structured[T: BaseModel](
    model: ChatModel, messages: Sequence[Message], schema: type[T]
) -> StructuredAnswer[T]:
    first = model.complete(messages, json_output=True)
    value, problem = _parse(first.text, schema)
    if value is not None:
        return _answer(value, [first], repaired=False)

    logger.warning(
        "%s answer from %s was invalid, asking for one repair", schema.__name__, first.model
    )
    repair = load_prompt("json_repair", "v1").text.replace("{errors}", problem)
    second = model.complete(
        [
            *messages,
            {"role": "assistant", "content": first.text},
            {"role": "user", "content": repair},
        ],
        json_output=True,
    )
    value, problem = _parse(second.text, schema)
    if value is None:
        raise StructuredOutputError(f"no valid answer after one repair: {problem}")
    return _answer(value, [first, second], repaired=True)


def _answer[T: BaseModel](
    value: T, calls: list[Completion], *, repaired: bool
) -> StructuredAnswer[T]:
    usage = TokenUsage()
    for call in calls:
        usage += call.usage or TokenUsage()
    return StructuredAnswer(
        value=value,
        model=calls[-1].model,
        repaired=repaired,
        usage=usage,
        latency_seconds=sum(call.latency_seconds for call in calls),
    )


def _parse[T: BaseModel](text: str, schema: type[T]) -> tuple[T | None, str]:
    """Return the object, or None and a description of what is wrong with the answer."""
    stripped = text.strip()
    fenced = _FENCE.match(stripped)
    if fenced:
        stripped = fenced.group(1)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return None, f"The answer was not valid JSON: {exc.msg} at line {exc.lineno}."
    try:
        return schema.model_validate(data), ""
    except ValidationError as exc:
        lines = [
            f"- {'.'.join(map(str, error['loc'])) or 'answer'}: {error['msg']}"
            for error in exc.errors()
        ]
        return None, "The answer did not match the schema:\n" + "\n".join(lines)
