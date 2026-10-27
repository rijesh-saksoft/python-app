"""The /ask endpoint: the place where you build the grounded assistant (days 9 to 14)."""

from fastapi import APIRouter

from app.models.schemas import AskRequest, AskResponse
from app.services import answering

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest) -> AskResponse:
    """Thin router: validate (done by Pydantic), call the service, return the result."""
    return answering.answer_question(body.question)
