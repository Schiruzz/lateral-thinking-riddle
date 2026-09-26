"""Checks of the judge's deterministic guards with a fake model: no API calls."""

import json
from types import SimpleNamespace

import pytest

from riddle.judge import VERIFY_CONFIG, Judge
from riddle.puzzle import load_puzzle


class FakeModels:
    """Stands in for `client.models`: canned judge verdicts, verifier answers by card text."""

    def __init__(self, verdicts, stated):
        self.verdicts = list(verdicts)   # returned in order, one per judge call
        self.stated = stated             # card or element text -> verifier answer
        self.judge_calls = []
        self.verify_calls = []

    def generate_content(self, model, contents, config):
        """Answer as the verifier or as the judge, depending on the config."""
        if config is VERIFY_CONFIG:
            self.verify_calls.append(contents)
            text = contents.split("CARD: ")[-1]
            return SimpleNamespace(text=json.dumps({"stated": self.stated.get(text, False)}))
        self.judge_calls.append(contents)
        return SimpleNamespace(text=json.dumps(self.verdicts.pop(0)))


def verdict(answer, cards=(), elements=(), positive="question"):
    """Build a judge verdict; cards are (quote, id) pairs."""
    return {"positive_question": positive, "answer": answer,
            "cards": [{"quote": quote, "id": cid} for quote, cid in cards],
            "solution_elements": list(elements)}


def make_judge(puzzle, verdicts, stated=None):
    """Build a judge whose model is a FakeModels; return both."""
    models = FakeModels(verdicts, stated or {})
    return Judge(puzzle, SimpleNamespace(models=models)), models


@pytest.fixture
def puzzle():
    """The gabbiano puzzle."""
    return load_puzzle("gabbiano", "it")


def test_invalid_answer_unlocks_nothing(puzzle):
    """An invalid question never unlocks cards, whatever the judge proposes."""
    judge, _ = make_judge(puzzle, [verdict("invalid", [("figlio", "figlio")])])
    assert judge.judge("La soluzione riguarda il figlio?", [], [])["cards"] == []


def test_quote_missing_from_the_question_is_dropped(puzzle):
    """A card whose quote is not in the player's words is dropped before verification."""
    judge, models = make_judge(puzzle, [verdict("yes", [("carne umana", "carne_umana")])])
    assert judge.judge("C'entra la carne?", [], [])["cards"] == []
    assert models.verify_calls == []


def test_key_card_needs_its_word(puzzle):
    """cieco stays hidden without a blindness word, even if both models agree."""
    judge, _ = make_judge(puzzle, [verdict("yes", [("problemi alla vista", "cieco")])],
                          {puzzle.card_text["cieco"]: True})
    assert judge.judge("Ha problemi alla vista?", [], [])["cards"] == []


def test_verifier_decides_facts(puzzle):
    """A fact proposed by the judge is dropped when the verifier rejects it."""
    judge, _ = make_judge(puzzle, [verdict("yes", [("isola", "isola")])],
                          {puzzle.card_text["isola"]: False})
    assert judge.judge("Sono finiti su un'isola?", [], [])["cards"] == []


def test_exclusions_skip_verification(puzzle):
    """An exclusion follows from a "no" and is kept without calling the verifier."""
    judge, models = make_judge(puzzle, [verdict("no", [("carne", "carne_ok")])])
    assert judge.judge("La carne era avariata?", [], [])["cards"] == ["carne_ok"]
    assert models.verify_calls == []


def test_negated_question_is_judged_again_in_positive_form(puzzle):
    """A question with "non" is judged a second time, and the second verdict counts."""
    first = verdict("no", positive="È sua moglie?")
    second = verdict("yes", [("sua moglie", "moglie")], positive="È sua moglie?")
    judge, models = make_judge(puzzle, [first, second], {puzzle.card_text["moglie"]: True})
    result = judge.judge("Non è sua moglie?", [], [])
    assert len(models.judge_calls) == 2
    assert result["answer"] == "yes"
    assert result["cards"] == ["moglie"]


def test_solution_needs_every_element(puzzle):
    """The solution is won only when every element is confirmed by the verifier."""
    elements = puzzle.solution_elements
    judge, _ = make_judge(puzzle, [verdict("yes", elements=["figlio_mangiato"])],
                          {elements["figlio_mangiato"]: True})
    assert puzzle.root not in judge.judge("Ha mangiato suo figlio?", [], [])["cards"]

    judge, _ = make_judge(puzzle, [verdict("yes", elements=["figlio_mangiato"])],
                          {text: True for text in elements.values()})
    assert puzzle.root in judge.judge("Al ristorante ha capito di aver mangiato suo figlio", [], [])["cards"]


def test_links_are_verified_without_context(puzzle):
    """A deduction must be in the player's words: its check gets no context."""
    judge, models = make_judge(puzzle, [verdict("yes", [("mentito per salvarlo", "d_pieta")])],
                               {puzzle.card_text["d_pieta"]: True})
    result = judge.judge("La moglie gli ha mentito per salvarlo?", [("Gli ha mentito?", "yes")],
                         ["bugia", "motivo", "moglie"])
    assert result["cards"] == ["d_pieta"]
    assert models.verify_calls[0].startswith(judge.no_context)