"""Answering logic. Starts as a safe stub and grows into the RAG service.

Rule for AI features (Playbook AI-06): answer only from retrieved sources, and say so
when the sources do not support an answer.  The stub below always refuses, which is the
safe default until retrieval exists.
"""

from app.models.schemas import AskResponse


def answer_question(question: str) -> AskResponse:
    """TODO(trainee, days 6 to 11): retrieve allowed chunks, build the context, call the model.

    Steps to build here:
      1. retrieve chunks the current user may see (permission filter BEFORE ranking, AI-08)
      2. build a context that fits the budget
      3. call the model through your provider-agnostic client (AI-01), with a timeout
      4. return the answer with citations; return "I don't know" when support is missing
    """
    return AskResponse(answer="I don't know. No sources are available yet.", citations=[])
