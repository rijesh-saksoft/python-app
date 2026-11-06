"""The shape a CV is extracted into. Model output is untrusted, so the schema is strict:
unknown fields are rejected and years must be plausible."""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Year = Annotated[int, Field(ge=1950, le=2100)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Job(_Strict):
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    start_year: Year
    end_year: Year | None = None  # None when the job is current

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        if self.end_year is not None and self.end_year < self.start_year:
            raise ValueError("end_year is before start_year")
        return self


class Education(_Strict):
    degree: str = Field(min_length=1)
    graduation_year: Year | None = None


class CandidateProfile(_Strict):
    name: str = Field(min_length=1)
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = None
    location: str | None = None
    years_experience: int | None = Field(default=None, ge=0, le=70)
    skills: list[str] = []
    jobs: list[Job] = []
    education: list[Education] = []
