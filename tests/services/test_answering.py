import json
from collections.abc import Sequence

from app.services.answering import NO_ANSWER, answer_from_passages
from app.services.chunking import Chunk
from app.services.llm_client import Completion, Message, TokenUsage

TRAVEL = Chunk(doc="05_travel.md", index=4, text="On a trip with an overnight stay: 60 per day.")
EXPENSES = Chunk(doc="06_expenses.md", index=1, text="Meals without an overnight stay: 25.")


class FakeModel:
    def __init__(self, reply: dict[str, object]) -> None:
        self.reply = json.dumps(reply)
        self.seen: list[Sequence[Message]] = []

    def complete(self, messages: Sequence[Message], *, json_output: bool = False) -> Completion:
        self.seen.append(messages)
        return Completion(self.reply, "fake-model", TokenUsage(10, 5), "stop", 0.1)


def test_answer_cites_the_passages_the_model_used() -> None:
    model = FakeModel({"supported": True, "answer": "Up to 60 per day.", "passage_ids": [1]})

    response = answer_from_passages(model, "Meal limit overnight?", [TRAVEL, EXPENSES])

    assert response.answer == "Up to 60 per day."
    assert [(c.source, c.passage) for c in response.citations] == [("05_travel.md", TRAVEL.text)]


def test_question_and_passages_reach_the_model_as_json_data() -> None:
    model = FakeModel({"supported": True, "answer": "60.", "passage_ids": [1]})

    answer_from_passages(model, "Meal limit overnight?", [TRAVEL])

    data = json.loads(str(model.seen[0][-1]["content"]))
    assert data == {
        "question": "Meal limit overnight?",
        "passages": [{"id": 1, "source": "05_travel.md", "text": TRAVEL.text}],
    }


def test_unsupported_answer_says_i_do_not_know() -> None:
    model = FakeModel({"supported": False, "answer": "Probably 40.", "passage_ids": []})

    response = answer_from_passages(model, "Hotel limit in Paris?", [TRAVEL])

    assert response.answer == NO_ANSWER
    assert response.citations == []


def test_invented_passage_ids_are_ignored() -> None:
    model = FakeModel({"supported": True, "answer": "60.", "passage_ids": [1, 7]})

    response = answer_from_passages(model, "Meal limit overnight?", [TRAVEL])

    assert [c.source for c in response.citations] == ["05_travel.md"]


def test_answer_citing_only_invented_passages_says_i_do_not_know() -> None:
    model = FakeModel({"supported": True, "answer": "40.", "passage_ids": [9]})

    response = answer_from_passages(model, "Meal limit overnight?", [TRAVEL])

    assert response.answer == NO_ANSWER


def test_no_passages_means_no_model_call() -> None:
    model = FakeModel({"supported": True, "answer": "40.", "passage_ids": [1]})

    response = answer_from_passages(model, "Meal limit overnight?", [])

    assert response.answer == NO_ANSWER
    assert model.seen == []
