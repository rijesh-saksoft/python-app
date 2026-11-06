import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.models.cv import CandidateProfile
from app.services.cv_evaluation import (
    FIELDS,
    CvRun,
    EvaluationResult,
    GoldFileError,
    format_table,
    load_gold,
    run_evaluation,
    score_profile,
    summarise,
)
from app.services.cv_extractor import CvExtractor
from app.services.llm_client import Completion, Message, TokenUsage

GOLD = CandidateProfile.model_validate(
    {
        "name": "Asha Alder",
        "email": "asha.alder@example.com",
        "phone": "+00 555 588 8287",
        "location": "Kochi",
        "years_experience": 1,
        "skills": ["SQL", "Git", "AWS basics"],
        "jobs": [
            {"title": "Dev", "company": "Stonebridge", "start_year": 2022, "end_year": 2024},
            {"title": "QA", "company": "Pinewood", "start_year": 2020, "end_year": 2022},
        ],
        "education": [{"degree": "MCA", "graduation_year": 2019}],
    }
)


def changed(**fields: object) -> CandidateProfile:
    return GOLD.model_copy(update=fields)


def wrong_fields(predicted: CandidateProfile) -> list[str]:
    return [field for field, right in score_profile(predicted, GOLD).items() if not right]


class FakeModel:
    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)

    def complete(self, messages: Sequence[Message], *, json_output: bool = False) -> Completion:
        return Completion(
            text=self.answers.pop(0),
            model="fake-model",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
            finish_reason="stop",
            latency_seconds=2.0,
        )


def test_identical_profile_scores_every_field() -> None:
    assert score_profile(GOLD, GOLD) == dict.fromkeys(FIELDS, True)


def test_text_ignores_capitals_and_extra_spaces() -> None:
    assert wrong_fields(changed(name="  asha   ALDER ", location="kochi")) == []


def test_phone_compares_digits_only() -> None:
    assert wrong_fields(changed(phone="+00-555-588-8287")) == []
    assert wrong_fields(changed(phone="+00 555 588 8288")) == ["phone"]


def test_skills_ignore_order_but_not_missing_items() -> None:
    assert wrong_fields(changed(skills=["aws basics", "Git", "SQL"])) == []
    assert wrong_fields(changed(skills=["SQL", "Git"])) == ["skills"]


def test_jobs_must_match_in_order_with_years() -> None:
    swapped = changed(jobs=list(reversed(GOLD.jobs)))
    wrong_year = changed(jobs=[GOLD.jobs[0].model_copy(update={"end_year": 2023}), GOLD.jobs[1]])

    assert wrong_fields(swapped) == ["jobs"]
    assert wrong_fields(wrong_year) == ["jobs"]


def test_missing_value_is_wrong() -> None:
    assert wrong_fields(changed(email=None, years_experience=None)) == [
        "email",
        "years_experience",
    ]


def test_load_gold_accepts_a_filled_file(tmp_path: Path) -> None:
    path = tmp_path / "cv_01.json"
    path.write_text(GOLD.model_dump_json(), encoding="utf-8")

    assert load_gold(path) == GOLD


@pytest.mark.parametrize(
    "unfilled",
    [
        {"name": ""},
        {"skills": []},
        {"jobs": [{"title": "", "company": "X", "start_year": 2020, "end_year": 2021}]},
        {"education": [{"degree": "MCA", "graduation_year": "2019"}, {"degree": ""}]},
    ],
)
def test_load_gold_refuses_an_unfilled_file(tmp_path: Path, unfilled: dict[str, object]) -> None:
    path = tmp_path / "cv_01.json"
    path.write_text(json.dumps({**GOLD.model_dump(), **unfilled}), encoding="utf-8")

    with pytest.raises(GoldFileError, match=r"cv_01\.json"):
        load_gold(path)


def test_run_evaluation_scores_and_records_failures() -> None:
    model = FakeModel(GOLD.model_dump_json(), "not json", "still not json")
    cases = [("cv_01", "Asha Alder CV", GOLD), ("cv_02", "Another CV", GOLD)]

    runs = run_evaluation(CvExtractor(model), cases)

    assert runs[0].fields == dict.fromkeys(FIELDS, True)
    assert runs[0].profile == GOLD
    assert runs[0].model == "fake-model"
    assert runs[1].fields is None
    assert runs[1].error is not None
    assert "after one repair" in runs[1].error


def test_summarise_counts_failures_as_wrong() -> None:
    good = CvRun(
        cv_id="cv_01",
        fields=dict.fromkeys(FIELDS, True),
        repaired=True,
        latency_seconds=2.0,
        prompt_tokens=100,
        completion_tokens=50,
    )
    half = good.model_copy(
        update={"cv_id": "cv_02", "fields": {f: i % 2 == 0 for i, f in enumerate(FIELDS)}}
    )
    failed = CvRun(cv_id="cv_03", error="no valid answer", latency_seconds=8.0)
    result = EvaluationResult(model="m", prompt_version="cv_extract/v1", runs=[good, half, failed])

    report = summarise(result)

    assert report.cvs == 3
    assert report.field_accuracy == pytest.approx(12 / 24)
    assert report.per_field["name"] == pytest.approx(2 / 3)
    assert report.per_field["email"] == pytest.approx(1 / 3)
    assert report.failures == 1
    assert report.repairs == 2
    assert report.median_latency_seconds == 2.0
    assert report.prompt_tokens == 200


def test_run_evaluation_marks_cvs_without_gold_as_unscored() -> None:
    model = FakeModel(GOLD.model_dump_json(), "not json", "still not json")
    cases = [("cv_11", "Extra CV", None), ("cv_12", "Another extra CV", None)]

    runs = run_evaluation(CvExtractor(model), cases)

    assert [run.scored for run in runs] == [False, False]
    assert runs[0].profile == GOLD
    assert runs[1].error is not None


def test_summarise_leaves_out_unscored_cvs() -> None:
    scored = CvRun(cv_id="cv_01", fields=dict.fromkeys(FIELDS, True), latency_seconds=1.0)
    extra = CvRun(cv_id="cv_11", scored=False, profile=GOLD, latency_seconds=9.0)
    failed_extra = CvRun(cv_id="cv_12", scored=False, error="HTTP 429")
    result = EvaluationResult(
        model="m", prompt_version="cv_extract/v1", runs=[scored, extra, failed_extra]
    )

    report = summarise(result)

    assert report.cvs == 1
    assert report.field_accuracy == 1.0
    assert report.failures == 0
    assert report.median_latency_seconds == 1.0


def test_format_table_has_one_column_per_model() -> None:
    run = CvRun(
        cv_id="cv_01",
        fields=dict.fromkeys(FIELDS, True),
        latency_seconds=1.5,
        prompt_tokens=10,
        completion_tokens=5,
    )
    reports = [
        summarise(EvaluationResult(model=name, prompt_version="cv_extract/v1", runs=[run]))
        for name in ("hosted-model", "local-model")
    ]

    table = format_table(reports)

    assert table.splitlines()[0] == "| Measure | hosted-model | local-model |"
    assert "| Field accuracy | 100.0% | 100.0% |" in table
    assert "| skills | 100.0% | 100.0% |" in table
