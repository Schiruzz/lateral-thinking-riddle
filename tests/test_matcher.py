"""Checks of the matcher on the card schema with a fake model: no API calls."""

import json
from types import SimpleNamespace

import pytest

from riddle.engine import Session
from riddle.judge import VERIFY_CONFIG, Matcher
from riddle.schema import load_riddle


class FakeModels:
    """Stands in for `client.models`: one canned matcher output, verifier answers by fact text."""

    def __init__(self, items, stated):
        self.items = items     # (quote, id) pairs the matcher returns
        self.stated = stated   # fact text -> verifier answer
        self.matcher_calls = []
        self.verify_calls = []

    def generate_content(self, model, contents, config):
        """Answer as the verifier or as the matcher, depending on the config."""
        if config is VERIFY_CONFIG:
            self.verify_calls.append(contents)
            text = contents.split("CARD: ")[-1]
            return SimpleNamespace(text=json.dumps({"stated": self.stated.get(text, False)}))
        self.matcher_calls.append(config)
        return SimpleNamespace(text=json.dumps({"items": [{"quote": q, "id": i} for q, i in self.items]}))


def make_matcher(riddle, items=(), stated=None, use_verifier=True):
    """Build a matcher whose model is a FakeModels; return both."""
    models = FakeModels(items, stated or {})
    return Matcher(riddle, SimpleNamespace(models=models), use_verifier=use_verifier), models


def verdict(answer, question):
    """Build an arbiter verdict."""
    return {"positive_question": question, "answer": answer}


@pytest.fixture
def baita():
    return load_riddle("baita", "it")


@pytest.mark.parametrize("answer", ["irrelevant", "invalid", "unclear"])
def test_answers_without_content_state_nothing(baita, answer):
    matcher, models = make_matcher(baita)
    assert matcher.match("Erano vecchi?", verdict(answer, "Erano vecchi?"), [], Session(baita)) == ([], [])
    assert models.matcher_calls == []


def test_quote_missing_from_the_question_is_dropped(baita):
    matcher, models = make_matcher(baita, [("una stufa", "stufa")])
    question = "C'era un camino?"
    assert matcher.match(question, verdict("yes", question), [], Session(baita)) == ([], [])
    assert models.verify_calls == []


def test_verifier_decides_key_facts(baita):
    question = "È morto avvelenato da un gas?"
    matcher, _ = make_matcher(baita, [("avvelenato da un gas", "gas")])
    assert matcher.match(question, verdict("yes", question), [], Session(baita)) == ([], [])
    matcher, _ = make_matcher(baita, [("avvelenato da un gas", "gas")],
                              stated={baita.facts["gas"]["text"]: True})
    assert matcher.match(question, verdict("yes", question), [], Session(baita)) == (["gas"], [])


def test_steps_skip_verification(baita):
    question = "Si è chiuso lui a chiave?"
    matcher, models = make_matcher(baita, [("chiuso lui a chiave", "porta_lui")])
    assert matcher.match(question, verdict("yes", question), [], Session(baita)) == (["porta_lui"], [])
    assert models.verify_calls == []


def test_without_verifier_the_matcher_decides_alone(baita):
    question = "Si è chiuso lui a chiave?"
    matcher, models = make_matcher(baita, [("chiuso lui a chiave", "porta_lui")], use_verifier=False)
    assert matcher.match(question, verdict("yes", question), [], Session(baita)) == (["porta_lui"], [])
    assert models.verify_calls == []


def test_false_leads_skip_verification(baita):
    question = "C'era un passaggio segreto?"
    matcher, models = make_matcher(baita, [("passaggio segreto", "passaggio")])
    assert matcher.match(question, verdict("no", question), [], Session(baita)) == ([], ["passaggio"])
    assert models.verify_calls == []


def test_false_leads_are_offered_only_after_no(baita):
    question = "È morto di freddo?"
    matcher, models = make_matcher(baita)
    matcher.match(question, verdict("yes", question), [], Session(baita))
    assert baita.exclusions["freddo"]["text"] not in models.matcher_calls[0].system_instruction


def test_found_facts_are_not_offered_again(baita):
    session = Session(baita)
    session.unlock(["stufa"])
    question = "La stufa era accesa?"
    matcher, models = make_matcher(baita)
    matcher.match(question, verdict("yes", question), [], session)
    assert f"stufa: {baita.facts['stufa']['text']}" not in models.matcher_calls[0].system_instruction


def test_a_fact_after_a_no_is_verified_even_if_not_key(baita):
    question = "È morto per cause naturali?"
    matcher, models = make_matcher(baita, [("cause naturali", "incidente")])   # the verifier says no by default
    assert matcher.match(question, verdict("no", question), [], Session(baita)) == ([], [])
    assert len(models.verify_calls) == 1


def test_victory_is_judged_on_what_the_sentence_claims_even_after_a_no(baita):
    question = "È morto per il fumo della stufa?"
    matcher, models = make_matcher(baita, stated={baita.victory["v_gas"]["claim"]: True})
    assert matcher.stated_victory(verdict("no", question), [], Session(baita)) == ["v_gas"]
    assert all("ANSWER: yes" in call for call in models.verify_calls)   # judged as if the answer were yes