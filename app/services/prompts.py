"""Load prompts from versioned files (Playbook AI-04).

A prompt is reviewed and changed like code. A change gets a new version file instead of an
edit, so every stored result can say exactly which prompt produced it (AI-03).
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_SAFE_NAME = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    version: str
    text: str

    @property
    def id(self) -> str:
        return f"{self.name}/{self.version}"


@lru_cache
def load_prompt(name: str, version: str) -> Prompt:
    if not (_SAFE_NAME.match(name) and _SAFE_NAME.match(version)):
        raise ValueError(f"invalid prompt name or version: {name!r} {version!r}")
    text = (PROMPTS_DIR / name / f"{version}.txt").read_text(encoding="utf-8")
    return Prompt(name=name, version=version, text=text)
