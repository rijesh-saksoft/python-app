"""Count tokens through the chat API. Every provider reports prompt_tokens, so no tokenizer
package is needed, and each model is measured with its own tokenizer.

The reported count also includes the chat template the provider wraps around a message. That
overhead is measured once with a one-character message and taken off every text.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.services.llm_client import LlmClient

PROBE = "."


class TokenCountError(Exception):
    """The provider did not report how many tokens the prompt used."""


@dataclass(frozen=True, slots=True)
class TokenCount:
    name: str
    text: str
    tokens: int

    @property
    def chars_per_token(self) -> float:
        return len(self.text) / self.tokens


def _prompt_tokens(llm: LlmClient, text: str) -> int:
    completion = llm.complete([{"role": "user", "content": text}], max_tokens=1)
    if completion.usage is None:
        raise TokenCountError(f"model {completion.model} reports no token usage")
    return completion.usage.prompt_tokens


def count_tokens(llm: LlmClient, texts: Mapping[str, str]) -> list[TokenCount]:
    overhead = _prompt_tokens(llm, PROBE) - 1
    return [
        TokenCount(name=name, text=text, tokens=_prompt_tokens(llm, text) - overhead)
        for name, text in texts.items()
    ]


def format_table(counts: list[TokenCount]) -> str:
    lines = [
        "| Text | Characters | Words | Tokens | Characters per token |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {c.name} | {len(c.text)} | {len(c.text.split())} | {c.tokens} "
        f"| {c.chars_per_token:.1f} |"
        for c in counts
    ]
    return "\n".join(lines)
