"""Checks of the conductor with a fake model: no API calls."""

import json
from types import SimpleNamespace

import pytest

from riddle.conductor import STUCK_LINES, WRONG_PART_LINES, Conductor, pick_line
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


def test_an_irrelevant_joke_must_say_it_does_not_matter(baita):
    result, _ = reply(baita, ("Magari era biondo.", "", ""), "Era biondo?", answer="irrelevant")
    assert result["reply"] == "Non conta per la storia."


def test_an_irrelevant_joke_cannot_hide_a_yes(baita):
    joke = "Probabilmente sì, se avessero fatto un corso. Ma per la storia non conta niente."
    result, _ = reply(baita, (joke, "", ""), "Potevano evitarlo?", answer="irrelevant")
    assert result["reply"] == "Non conta per la storia."


def test_a_stuck_line_is_never_said_twice_in_a_game():
    said_before = [f"No. {line}" for line in STUCK_LINES[:-1]]
    assert pick_line(STUCK_LINES, said_before) == STUCK_LINES[-1]


def test_a_line_with_a_number_is_recognised_once_said():
    bank = ["Dopo ben {n} domande vaghe, abbiamo novità:", "Era ora!"]
    assert pick_line(bank, ["Dopo ben 7 domande vaghe, abbiamo novità: sì."]) == "Era ora!"


def test_a_joke_counts_in_whatever_field_the_model_wrote_it(baita):
    joke = "Mah, magari avevano ottant'anni. Ma per la storia non conta niente."
    result, _ = reply(baita, ("", joke, ""), "Erano vecchi gli amici?", answer="irrelevant")
    assert result["reply"] == joke


def test_c_era_is_a_pointer_not_a_new_word(baita):
    result, _ = reply(baita, ("", "No, non c'era.", ""), "Aveva un camino nella stanza?", answer="no")
    assert result["reply"] == "No, non c'era."



def relief_reply(riddle, monkeypatch, line):
    """Run the conductor on a yes that finds a fact after five empty questions, with one line in the relief bank."""
    monkeypatch.setattr("riddle.conductor.RELIEF_LINES", [line])
    session = Session(riddle)
    for n in range(1, 6):
        session.record(f"Domanda {n}?", [], "no")
    new = session.unlock(["stufa"])
    state = session.record("C'era una stufa?", new, "yes")
    models = FakeModels("Finalmente!", "Sì, c'era.", "")
    return Conductor(riddle, SimpleNamespace(models=models)).reply(
        "C'era una stufa?", {"positive_question": "C'era una stufa?", "answer": "yes"}, [], session, new, state)


def test_the_relief_opening_comes_from_the_bank_not_the_model(baita, monkeypatch):
    assert relief_reply(baita, monkeypatch, "Era ora!")["reply"] == "Era ora! Sì, c'era."


def test_a_relief_line_with_a_yes_is_the_whole_answer(baita, monkeypatch):
    assert relief_reply(baita, monkeypatch, "Fermate tutto: è un sì!")["reply"] == "Fermate tutto: è un sì!"


def test_a_relief_line_with_a_colon_counts_the_questions(baita, monkeypatch):
    result = relief_reply(baita, monkeypatch, "Dopo ben {n} domande vaghe, abbiamo novità:")
    assert result["reply"] == "Dopo ben 5 domande vaghe, abbiamo novità: sì, c'era."


def test_a_relaunch_asks_the_why_of_the_next_element_without_the_model(baita):
    session = Session(baita)
    state = session.record("È stata la stufa a ucciderlo?", [], "yes", ["v_gas"])
    models = FakeModels("", "Sì.", "")
    result = Conductor(baita, SimpleNamespace(models=models)).reply(
        "È stata la stufa a ucciderlo?", {"positive_question": "È stata la stufa a ucciderlo?", "answer": "yes"},
        [], session, [], state)
    assert result["reply"].endswith("perché il fumo è rimasto nella stanza, quella notte?")
    assert models.calls == []


def test_an_explanation_with_a_wrong_part_says_so_without_saying_which(baita):
    session = Session(baita)
    question = "È morto per il fumo della stufa accesa da un amico?"
    state = session.record(question, [], "no", ["v_gas"])
    result = Conductor(baita, SimpleNamespace(models=FakeModels("", "No.", ""))).reply(
        question, {"positive_question": question, "answer": "no"}, [], session, [], state)
    assert result["reply"] in WRONG_PART_LINES