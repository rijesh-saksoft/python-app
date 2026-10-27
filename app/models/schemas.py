"""Data shapes at the edges of the service (Playbook PY-11).

Pydantic checks every request and response, so bad data is rejected at the door.
"""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    # Limit the size of input (SEC-09, SEC-15): a 10,000 character question is not a question.
    question: str = Field(min_length=1, max_length=2000)


class Citation(BaseModel):
    source: str
    passage: str


class AskResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
