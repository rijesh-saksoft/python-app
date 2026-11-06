"""Score CV extraction against answers written by hand (Playbook AI-03: numbers, not opinions).

Each CV has eight fields, each right or wrong. A failed extraction counts every field as
wrong, so a model that often fails cannot look accurate by being scored only on its
successes.
"""

import json
import logging
import re
import statistics
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.models.cv import CandidateProfile
from app.services.cv_extractor import CvExtractionError, CvExtractor
from app.services.llm_client import LlmError

logger = logging.getLogger(__name__)

FIELDS = (
    "name",
    "email",
    "phone",
    "location",
    "years_experience",
    "skills",
    "jobs",
    "education",
)


class GoldFileError(Exception):
    """A gold file is missing, unfilled or does not match the schema."""


class CvRun(BaseModel):
    """One CV through one model. `fields` is None when the extraction failed or there is
    no gold answer; `scored` is False for CVs without a gold answer."""

    cv_id: str
    scored: bool = True
    model: str | None = None  # the model that answered: a fallback model if one was used
    fields: dict[str, bool] | None = None
    profile: CandidateProfile | None = None
    error: str | None = None
    repaired: bool = False
    latency_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class EvaluationResult(BaseModel):
    model: str
    prompt_version: str
    runs: list[CvRun]


@dataclass(frozen=True, slots=True)
class ModelReport:
    model: str
    prompt_version: str
    cvs: int
    field_accuracy: float
    per_field: dict[str, float]
    failures: int
    repairs: int
    median_latency_seconds: float
    total_seconds: float
    prompt_tokens: int
    completion_tokens: int


def _text(value: str | None) -> str | None:
    return " ".join(value.split()).casefold() if value is not None else None


def _digits(value: str | None) -> str | None:
    return re.sub(r"\D", "", value) if value is not None else None


_COMPARE: dict[str, Callable[[CandidateProfile], object]] = {
    "name": lambda p: _text(p.name),
    "email": lambda p: _text(p.email),
    "phone": lambda p: _digits(p.phone),
    "location": lambda p: _text(p.location),
    "years_experience": lambda p: p.years_experience,
    "skills": lambda p: {_text(skill) for skill in p.skills},
    "jobs": lambda p: [
        (_text(job.title), _text(job.company), job.start_year, job.end_year) for job in p.jobs
    ],
    "education": lambda p: [(_text(e.degree), e.graduation_year) for e in p.education],
}


def score_profile(predicted: CandidateProfile, gold: CandidateProfile) -> dict[str, bool]:
    return {field: _COMPARE[field](predicted) == _COMPARE[field](gold) for field in FIELDS}


def _looks_unfilled(value: object) -> bool:
    if value == "" or value == []:
        return True
    if isinstance(value, dict):
        return any(_looks_unfilled(item) for item in value.values())
    if isinstance(value, list):
        return any(_looks_unfilled(item) for item in value)
    return False


def load_gold(path: Path) -> CandidateProfile:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoldFileError(f"{path.name}: cannot read: {exc}") from exc
    if _looks_unfilled(data):
        raise GoldFileError(f"{path.name}: still has empty values; fill it in first")
    try:
        return CandidateProfile.model_validate(data)
    except ValidationError as exc:
        fields = ", ".join(".".join(map(str, error["loc"])) for error in exc.errors())
        raise GoldFileError(f"{path.name}: does not match the schema ({fields})") from exc


def run_evaluation(
    extractor: CvExtractor, cases: Iterable[tuple[str, str, CandidateProfile | None]]
) -> list[CvRun]:
    """Extract each CV and score it against its gold answer, if it has one."""
    runs: list[CvRun] = []
    for cv_id, text, gold in cases:
        try:
            result = extractor.extract(text)
        except (CvExtractionError, LlmError) as exc:
            logger.warning("%s failed: %s", cv_id, exc)
            runs.append(
                CvRun(cv_id=cv_id, scored=gold is not None, error=f"{type(exc).__name__}: {exc}")
            )
            continue
        runs.append(
            CvRun(
                cv_id=cv_id,
                scored=gold is not None,
                model=result.model,
                fields=score_profile(result.profile, gold) if gold else None,
                profile=result.profile,
                repaired=result.repaired,
                latency_seconds=result.latency_seconds,
                prompt_tokens=result.usage.prompt_tokens,
                completion_tokens=result.usage.completion_tokens,
            )
        )
        logger.info("%s done in %.1fs", cv_id, result.latency_seconds)
    return runs


def summarise(result: EvaluationResult) -> ModelReport:
    runs = [run for run in result.runs if run.scored]
    per_field = {
        field: sum(bool(run.fields and run.fields[field]) for run in runs) / len(runs)
        for field in FIELDS
    }
    answered = [run.latency_seconds for run in runs if run.error is None]
    return ModelReport(
        model=result.model,
        prompt_version=result.prompt_version,
        cvs=len(runs),
        field_accuracy=sum(per_field.values()) / len(FIELDS),
        per_field=per_field,
        failures=sum(run.error is not None for run in runs),
        repairs=sum(run.repaired for run in runs),
        median_latency_seconds=statistics.median(answered) if answered else 0.0,
        total_seconds=sum(run.latency_seconds for run in runs),
        prompt_tokens=sum(run.prompt_tokens for run in runs),
        completion_tokens=sum(run.completion_tokens for run in runs),
    )


def format_table(reports: Sequence[ModelReport]) -> str:
    """A Markdown table with one column per model, ready for docs/test.md."""

    def row(label: str, values: Iterable[str]) -> str:
        return f"| {label} | {' | '.join(values)} |"

    lines = [
        row("Measure", (r.model for r in reports)),
        row("---", ("---" for _ in reports)),
        row("Prompt", (r.prompt_version for r in reports)),
        row("CVs", (str(r.cvs) for r in reports)),
        row("Field accuracy", (f"{r.field_accuracy:.1%}" for r in reports)),
        *(row(field, (f"{r.per_field[field]:.1%}" for r in reports)) for field in FIELDS),
        row("Failures", (str(r.failures) for r in reports)),
        row("Repairs used", (str(r.repairs) for r in reports)),
        row("Median seconds per CV", (f"{r.median_latency_seconds:.1f}" for r in reports)),
        row("Total seconds", (f"{r.total_seconds:.1f}" for r in reports)),
        row("Tokens in / out", (f"{r.prompt_tokens} / {r.completion_tokens}" for r in reports)),
    ]
    return "\n".join(lines)
