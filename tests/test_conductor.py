"""Checks of the conductor with a fake model: no API calls."""

import json
from types import SimpleNamespace

import pytest

from riddle.conductor import Conductor
from riddle.engine import Session
from riddle.schema import load_riddle


class FakeModels:
    """Stands in for `client.models`: returns canned parts and keeps what it was sent."""

    def __init__(self, before, answer, after):
        self.parts = {"before": before, "answer": answer, "after": after}
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(f"{config.system_instruction}\n{contents}")
        return SimpleNamespace(text=json.dumps(self.parts))


@pytest.fixture
def baita():
    return load_riddle("baita", "it")


def reply(riddle, parts, question, answer="yes", found=()):
    """Run the conductor on one question with a fake model; return its result and what the model saw."""
    models = FakeModels(*parts)
    session = Session(riddle)
    new = session.unlock(list(found))
    state = session.record(question, new)
    result = Conductor(riddle, SimpleNamespace(models=models)).reply(
        question, {"positive_question": question, "answer": answer}, [], session, new, state)
    return result, models.calls[0]


def test_the_conductor_never_sees_the_solution(baita):
    _, seen = reply(baita, ("", "Sì.", ""), "C'era una stufa?", found=["stufa"])
    assert baita.truth not in seen
    assert baita.facts["comignolo"]["text"] not in seen
    assert baita.facts["stufa"]["text"] in seen


def test_an_answer_with_words_the_player_did_not_say_becomes_plain(baita):
    result, _ = reply(baita, ("", "No, la neve non ha coperto nulla.", ""),
                      "Le impronte sono state coperte dalla neve?", answer="no")
    assert result["reply"] == "No." and result["plain_answer"]


def test_a_yes_cannot_add_a_negation(baita):
    result, _ = reply(baita, ("", "Sì, non era solo.", ""), "Era solo?")
    assert result["reply"] == "Sì."


def test_a_question_asked_to_the_game_is_answered_to_the_player(baita):
    sentence = "No, non devi."
    result, _ = reply(baita, ("", sentence, ""), "Devo capire chi l'ha ucciso?", answer="no")
    assert result["reply"] == sentence and not result["plain_answer"]


def test_a_no_with_more_words_needs_a_non(baita):
    result, _ = reply(baita, ("", "No, in bocca.", ""), "In bocca?", answer="no")
    assert result["reply"] == "No."


def test_a_pronoun_keeps_the_answer_vague(baita):
    question = "I quattro amici sono inutili in questo indovinello?"
    result, _ = reply(baita, ("", "No, non lo sono.", ""), question, answer="no")
    assert result["reply"] == "No, non lo sono." and not result["plain_answer"]


def test_without_a_reason_from_the_engine_there_is_no_reaction(baita):
    result, _ = reply(baita, ("Finalmente un po' di azione!", "Sì, nevicava.", ""), "Nevicava?")
    assert result["reply"] == "Sì, nevicava."


def test_a_reaction_naming_a_hidden_fact_is_dropped(baita):
    models = FakeModels("Te lo ripeto:", "sì.", "E il comignolo da qualche parte doveva sfogare.")
    session = Session(baita)
    session.record("C'era una stufa?", session.unlock(["stufa"]))
    state = session.record("C'era una stufa?", [])   # asked again: a reason to react
    result = Conductor(baita, SimpleNamespace(models=models)).reply(
        "C'era una stufa?", {"positive_question": "C'era una stufa?", "answer": "yes"}, [], session, [], state)
    assert result["reply"] == "Sì." and result["revealed"] == ["comignolo"]


def test_without_a_yes_or_no_the_reaction_is_the_sentence(baita):
    joke = "Diciamo che aveva i calzini a pois: per la storia non cambia nulla."
    result, _ = reply(baita, (joke, "", ""), "Era biondo?", answer="irrelevant")
    assert result["reply"] == joke