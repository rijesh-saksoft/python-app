from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Record(BaseModel):
    """Every record the API lists has an integer id; pagination relies on it."""

    # Ignore unknown fields so a new field on the server does not break the client.
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int = Field(gt=0)


class Parcel(Record):
    name: str = Field(min_length=1)
    status: Literal["active", "pending", "inactive"]
    category: str = Field(min_length=1)
    created: date


class ApiMeta(BaseModel):
    variant: int
    domain: str
    entity: str
    pagination: str
    total: int = Field(ge=0)


class OffsetPage(BaseModel):
    """The page envelope. Items stay raw here and are validated one by one."""

    items: list[dict[str, object]]
    offset: int = Field(ge=0)
    limit: int = Field(ge=0)
    total: int = Field(ge=0)
