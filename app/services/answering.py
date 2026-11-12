"""Answering logic. Starts as a safe stub and grows into the RAG service.

Rule for AI features (Playbook AI-06): answer only from retrieved sources, and say so
when the sources do not support an answer.  answer_from_passages does that for passages
already retrieved; answer_question, behind the API, still always refuses, which is the safe
default until retrieval with permission filters exists.
"""

import json
from collections.abc import Sequence

from pydantic import BaseModel, Field

from app.models.schemas import AskResponse, Citation
from app.services.chunking import Chunk
from app.services.prompts import load_prompt
from app.services.structured_output import ChatModel, complete_structured

NO_ANSWER = "I don't know. The available sources do not answer this question."


class _ModelAnswer(BaseModel):
    supported: bool
    answer: str = Field(max_length=2000)
    passage_ids: list[int]


def answer_question(question: str) -> AskResponse:
    """TODO(trainee, days 6 to 11): retrieve allowed chunks, build the context, call the model.

    Steps to build here:
      1. retrieve chunks the current user may see (permission filter BEFORE ranking, AI-08)
      2. build a context that fits the budget
      3. call the model through your provider-agnostic client (AI-01), with a timeout
      4. return the answer with citations; return "I don't know" when support is missing
    """
    return AskResponse(answer="I don't know. No sources are available yet.", citations=[])


def answer_from_passages(
    model: ChatModel, question: str, passages: Sequence[Chunk], prompt_version: str = "v2"
) -> AskResponse:
    """Answer from the given passages only, citing them; "I don't know" without support."""
    if not passages:
        return AskResponse(answer=NO_ANSWER)
    numbered = dict(enumerate(passages, start=1))
    # JSON keeps every passage a value: a document cannot close its own marker and add
    # instructions after it.
    data = {
        "question": question,
        "passages": [{"id": i, "source": c.doc, "text": c.text} for i, c in numbered.items()],
    }
    messages = [
        {"role": "system", "content": load_prompt("grounded_answer", prompt_version).text},
        {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
    ]
    reply = complete_structured(model, messages, _ModelAnswer).value

    # The model may cite ids it was never given; only real passages count as support.
    cited = [numbered[i] for i in dict.fromkeys(reply.passage_ids) if i in numbered]
    if not reply.supported or not cited:
        return AskResponse(answer=NO_ANSWER)
    return AskResponse(
        answer=reply.answer,
        citations=[Citation(source=c.doc, passage=c.text) for c in cited],
    )
