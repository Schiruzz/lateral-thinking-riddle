"""Checks of the conductor with a fake model: no API calls."""

import json
from types import SimpleNamespace

import pytest

from riddle.conductor import Conductor
from riddle.engine import Session
from riddle.schema import load_riddle


class FakeModels:
    """Stands in for `client.models`: returns a canned sentence and keeps what it was sent."""

    def __init__(self, sentence):
        self.sentence = sentence
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(f"{config.system_instruction}\n{contents}")
        return SimpleNamespace(text=json.dumps({"reply": self.sentence}))


@pytest.fixture
def baita():
    return load_riddle("baita", "it")


def reply(riddle, sentence, question, answer="yes", found=()):
    """Run the conductor on one question with a fake model; return its result and what the model saw."""
    models = FakeModels(sentence)
    session = Session(riddle)
    new = session.unlock(list(found))
    state = session.record(question, new)
    result = Conductor(riddle, SimpleNamespace(models=models)).reply(
        question, {"positive_question": question, "answer": answer}, [], session, new, state)
    return result, models.calls[0]


def test_the_conductor_never_sees_the_solution(baita):
    _, seen = reply(baita, "Sì.", "C'era una stufa?", found=["stufa"])
    assert baita.truth not in seen
    assert baita.facts["comignolo"]["text"] not in seen
    assert baita.facts["stufa"]["text"] in seen


def test_a_word_of_a_hidden_fact_sends_back_the_plain_answer(baita):
    result, _ = reply(baita, "Sì, e il comignolo da qualche parte doveva sfogare.", "C'era una stufa?",
                      found=["stufa"])
    assert result == {"reply": "Sì.", "revealed": ["comignolo"]}


def test_the_player_s_words_and_the_found_facts_are_allowed(baita):
    sentence = "Sì, il comignolo era bloccato. E la stufa era a legna."
    result, _ = reply(baita, sentence, "La neve ha bloccato il comignolo?", found=["comignolo"])
    assert result == {"reply": sentence, "revealed": []}