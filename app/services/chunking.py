"""Three ways to split a Markdown document into chunks for retrieval, to compare them.

- fixed_size: every N characters, with overlap. Ignores sentences and sections.
- by_section: one chunk per "##" section, with the document title and heading in front, so a
  fact such as "the limit is 25" keeps the context that says what the limit is for.
- by_sentences: N whole sentences per chunk. Headings are dropped.
"""

import re
from dataclasses import dataclass

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class Chunk:
    doc: str
    index: int
    text: str


def fixed_size(doc: str, text: str, size: int = 500, overlap: int = 100) -> list[Chunk]:
    if not 0 <= overlap < size:
        raise ValueError("overlap must be at least 0 and smaller than size")
    step = size - overlap
    pieces = [text[start : start + size] for start in range(0, len(text), step)]
    # Drop pieces that lie entirely inside the overlap of the one before.
    pieces = [p for i, p in enumerate(pieces) if i == 0 or i * step + overlap < len(text)]
    return _numbered(doc, pieces)


def by_section(doc: str, text: str) -> list[Chunk]:
    title = ""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.startswith("# "):
            title = line[2:].strip()
        else:
            sections[-1][1].append(line)
    pieces = []
    for heading, lines in sections:
        body = "\n".join(lines).strip()
        if body:
            label = f"{title} - {heading}" if heading else title
            pieces.append(f"{label}\n\n{body}")
    return _numbered(doc, pieces)


def by_sentences(doc: str, text: str, per_chunk: int = 3) -> list[Chunk]:
    prose = " ".join(line for line in text.splitlines() if not line.startswith("#"))
    sentences = SENTENCE_END.split(prose.strip())
    pieces = [
        " ".join(sentences[start : start + per_chunk])
        for start in range(0, len(sentences), per_chunk)
    ]
    return _numbered(doc, pieces)


def _numbered(doc: str, pieces: list[str]) -> list[Chunk]:
    return [Chunk(doc=doc, index=i, text=piece) for i, piece in enumerate(pieces)]
