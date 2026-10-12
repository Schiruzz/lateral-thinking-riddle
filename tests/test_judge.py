"""Checks of the arbiter's deterministic guards with a fake model: no API calls."""

import json
from types import SimpleNamespace

import httpx
import pytest

from riddle.judge import Judge
from riddle.puzzle import load_arbiter


class FakeModels:
    """Stands in for `client.models`: canned arbiter outputs, returned in order."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.arbiter_calls = []

    def generate_content(self, model, contents, config):
        """Answer as the arbiter."""
        self.arbiter_calls.append(contents)
        return SimpleNamespace(text=json.dumps(self.answers.pop(0)))


def answer(value, positive=""):
    """Build an arbiter output."""
    return {"positive_question": positive, "answer": value}


def make_judge(puzzle, answers=()):
    """Build a judge whose model is a FakeModels; return both."""
    models = FakeModels(answers)
    return Judge(puzzle, SimpleNamespace(models=models)), models


@pytest.fixture
def puzzle():
    """What the arbiter reads of the gabbiano riddle."""
    return load_arbiter("gabbiano", "it")


# ---------- answer: the arbiter and its guards ----------

def test_negated_question_is_judged_again_in_positive_form(puzzle):
    """A question with "non" is judged a second time, and the second verdict counts."""
    judge, models = make_judge(puzzle, [answer("no", "È sua moglie?"), answer("yes", "È sua moglie?")])
    assert judge.answer("Non è sua moglie?", [], [])["answer"] == "yes"
    assert len(models.arbiter_calls) == 2


def test_rewrite_with_words_the_player_did_not_say_is_unclear(puzzle):
    """A garbled question the arbiter "repaired" with new words counts as not understood."""
    judge, _ = make_judge(puzzle, [answer("yes", "Era cieco?")])
    assert judge.answer("era cieca la vista del menù quando", [], [])["answer"] == "unclear"


def test_rewrite_that_only_removes_words_is_kept(puzzle):
    """Dropping fillers like "secondo me" keeps the answer."""
    judge, _ = make_judge(puzzle, [answer("yes", "Era cieco?")])
    assert judge.answer("secondo me era cieco", [], [])["answer"] == "yes"


def test_positive_question_always_ends_with_a_question_mark(puzzle):
    """A transcription without "?" still reaches the matcher as a question."""
    judge, _ = make_judge(puzzle, [answer("no", "Il gabbiano era vivo")])
    assert judge.answer("il gabbiano era vivo", [], [])["positive_question"] == "Il gabbiano era vivo?"


def test_rewrite_that_only_adds_an_apostrophe_is_kept(puzzle):
    """The transcription writes "centra", the arbiter "c'entra": the same word."""
    judge, _ = make_judge(puzzle, [answer("partly", "Il ristorante c'entra?")])
    assert judge.answer("Il ristorante centra?", [], [])["answer"] == "partly"


def test_rewrite_that_splits_an_apostrophe_is_kept(puzzle):
    """The arbiter writes "un isola" for "un'isola": the same words."""
    judge, _ = make_judge(puzzle, [answer("yes", "Sono rimasti su un isola senza cibo")])
    assert judge.answer("Sono rimasti su un'isola senza cibo?", [], [])["answer"] == "yes"


@pytest.mark.parametrize("said, rewritten", [
    ("il morto e morto di infarto", "Il morto è morto di infarto?"),        # accent put back
    ("era gia morto prima della neve", "Era già morto prima della neve?"),  # accent put back
    ("e stato uno dei 4 amici", "È stato uno dei quattro amici?"),          # digit spelled out
    ("c e stata una fuga di gas", "C'è stata una fuga di gas?"),            # apostrophe and accent put back
])
def test_rewrite_that_only_fixes_spelling_is_kept(puzzle, said, rewritten):
    """Accents, digits and apostrophes put back by the arbiter are spelling, not new words."""
    judge, _ = make_judge(puzzle, [answer("no", rewritten)])
    assert judge.answer(said, [], [])["answer"] == "no"


def test_rewrite_that_changes_a_word_is_still_unclear(puzzle):
    """A transcription slip the arbiter repairs is a guess: "variata" is not "avariata"."""
    judge, _ = make_judge(puzzle, [answer("no", "La carne era avariata?")])
    assert judge.answer("la carne era variata", [], [])["answer"] == "unclear"


def test_arbiter_knows_the_truth_and_the_facts(puzzle):
    """The arbiter reads the whole hidden story and the facts in order of play."""
    judge, _ = make_judge(puzzle)
    prompt = judge.arbiter_config.system_instruction
    assert puzzle.solution in prompt
    assert all(fact in prompt for fact in puzzle.solution_facts)


# ---------- model calls ----------

def test_call_retries_after_a_timeout(puzzle, monkeypatch):
    """A call that times out is retried after a short wait instead of blocking the game."""
    monkeypatch.setattr("riddle.judge.time.sleep", lambda seconds: None)   # no real waiting in tests
    outputs = [httpx.ReadTimeout("timed out"), SimpleNamespace(text="ok")]

    def generate_content(model, contents, config):
        # first call times out, the second one answers
        output = outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output

    judge = Judge(puzzle, SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    assert judge._call("model", "contents", None).text == "ok"