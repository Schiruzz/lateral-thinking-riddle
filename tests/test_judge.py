"""Checks of the judge's deterministic guards with a fake model: no API calls."""

import json
from types import SimpleNamespace

import httpx
import pytest

from riddle.judge import VERIFY_CONFIG, Judge
from riddle.puzzle import load_puzzle


class FakeModels:
    """Stands in for `client.models`: canned arbiter and matcher outputs, verifier answers by card text."""

    def __init__(self, answers, matches, stated):
        self.answers = list(answers)   # arbiter outputs, returned in order
        self.matches = list(matches)   # matcher outputs, returned in order
        self.stated = stated           # card or element text -> verifier answer
        self.arbiter_calls = []
        self.matcher_calls = []
        self.verify_calls = []

    def generate_content(self, model, contents, config):
        """Answer as the verifier, the matcher or the arbiter, depending on the call."""
        if config is VERIFY_CONFIG:
            self.verify_calls.append(contents)
            text = contents.split("CARD: ")[-1]
            return SimpleNamespace(text=json.dumps({"stated": self.stated.get(text, False)}))
        if "ANSWER: " in contents:   # only the matcher receives the answer
            self.matcher_calls.append((contents, config))
            return SimpleNamespace(text=json.dumps(self.matches.pop(0)))
        self.arbiter_calls.append(contents)
        return SimpleNamespace(text=json.dumps(self.answers.pop(0)))


def answer(value, positive=""):
    """Build an arbiter output."""
    return {"positive_question": positive, "answer": value}


def match(cards=(), elements=()):
    """Build a matcher output; cards are (quote, id) pairs."""
    return {"cards": [{"quote": quote, "id": cid} for quote, cid in cards], "solution_elements": list(elements)}


def make_judge(puzzle, answers=(), matches=(), stated=None):
    """Build a judge whose model is a FakeModels; return both."""
    models = FakeModels(answers, matches, stated or {})
    return Judge(puzzle, SimpleNamespace(models=models)), models


@pytest.fixture
def puzzle():
    """The gabbiano puzzle."""
    return load_puzzle("gabbiano", "it")


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



def test_arbiter_never_sees_the_cards(puzzle):
    """The arbiter knows the solution facts but no card list: answering and finding cards stay apart."""
    judge, _ = make_judge(puzzle)
    prompt = judge.arbiter_config.system_instruction
    assert all(fact in prompt for fact in puzzle.solution_facts)
    assert puzzle.card_text["cieco"] not in prompt


# ---------- cards: the matcher, its guards and the verifier ----------

@pytest.mark.parametrize("value", ["invalid", "unclear", "irrelevant"])
def test_answers_without_content_unlock_nothing(puzzle, value):
    """Invalid, unclear or irrelevant questions unlock nothing and do not even call the matcher."""
    judge, models = make_judge(puzzle)
    assert judge.cards("La soluzione riguarda il figlio?", answer(value), [], []) == []
    assert models.matcher_calls == []


def test_matcher_never_sees_the_solution(puzzle):
    """The matcher reads question and answer only: the solution is not in its prompt."""
    judge, models = make_judge(puzzle, matches=[match()])
    judge.cards("Era cieco?", answer("yes", "Era cieco?"), [], [])
    _, config = models.matcher_calls[0]
    assert puzzle.solution_facts[0] not in config.system_instruction


def test_quote_missing_from_the_question_is_dropped(puzzle):
    """A card whose quote is not in the player's words is dropped before verification."""
    judge, models = make_judge(puzzle, matches=[match([("carne umana", "carne_umana")])])
    assert judge.cards("C'entra la carne?", answer("yes", "C'entra la carne?"), [], []) == []
    assert models.verify_calls == []


def test_quote_with_an_apostrophe_matches_the_transcription(puzzle):
    """The matcher quotes "c'entra", the player said "centra": the quote still counts."""
    judge, _ = make_judge(puzzle, matches=[match([("Il ristorante c'entra", "ristorante_no")])])
    assert judge.cards("Il ristorante centra?", answer("no", "Il ristorante c'entra?"), [], []) == ["ristorante_no"]


def test_quote_with_other_punctuation_still_counts(puzzle):
    """The matcher quotes with a comma where the player said "e": every quoted word was said, so it counts."""
    judge, _ = make_judge(puzzle, matches=[match([("annegato, loro sono finiti", "d_tragedia")])],
                          stated={puzzle.card_text["d_tragedia"]: True})
    question = "Il figlio è annegato e loro sono finiti su un'isola?"
    lit = ["naufragio", "isola", "figlio_morto"]
    assert judge.cards(question, answer("yes", question), [], lit) == ["d_tragedia"]


def test_empty_quote_is_dropped(puzzle):
    """A card proposed without any quoted word is dropped before verification."""
    judge, models = make_judge(puzzle, matches=[match([("", "isola")])])
    assert judge.cards("C'entra il mare?", answer("yes", "C'entra il mare?"), [], []) == []
    assert models.verify_calls == []



def test_key_card_needs_its_word(puzzle):
    """cieco stays hidden without a blindness word, even if matcher and verifier agree."""
    judge, _ = make_judge(puzzle, matches=[match([("problemi alla vista", "cieco")])],
                          stated={puzzle.card_text["cieco"]: True})
    assert judge.cards("Ha problemi alla vista?", answer("yes", "Ha problemi alla vista?"), [], []) == []


def test_verifier_decides_facts(puzzle):
    """A fact proposed by the matcher is dropped when the verifier rejects it."""
    judge, _ = make_judge(puzzle, matches=[match([("isola", "isola")])], stated={puzzle.card_text["isola"]: False})
    assert judge.cards("Sono finiti su un'isola?", answer("yes", "Sono finiti su un'isola?"), [], []) == []


def test_exclusions_skip_verification(puzzle):
    """An exclusion follows from a "no" and is kept without calling the verifier."""
    judge, models = make_judge(puzzle, matches=[match([("carne", "carne_ok")])])
    assert judge.cards("La carne era avariata?", answer("no", "La carne era avariata?"), [], []) == ["carne_ok"]
    assert models.verify_calls == []


def test_links_are_verified_without_context(puzzle):
    """A deduction must be in the player's words: its check gets no context."""
    judge, models = make_judge(puzzle, matches=[match([("mentito per salvarlo", "d_pieta")])],
                               stated={puzzle.card_text["d_pieta"]: True})
    question = "La moglie gli ha mentito per salvarlo?"
    cards = judge.cards(question, answer("yes", question), [("Gli ha mentito?", "yes")], ["bugia", "motivo", "moglie"])
    assert cards == ["d_pieta"]
    assert models.verify_calls[0].startswith(judge.no_context)


def test_verifier_sees_the_story(puzzle):
    """A fact is verified with the story in its context, so "la carne" means the gull he ordered."""
    judge, models = make_judge(puzzle, matches=[match([("sapore della carne era diverso", "sapore")])],
                               stated={puzzle.card_text["sapore"]: True})
    question = "Il sapore della carne era diverso?"
    judge.cards(question, answer("yes", question), [], [])
    assert puzzle.story in models.verify_calls[0]


def test_solution_needs_the_verified_element(puzzle):
    """Saying "capito" is not enough: the verifier must confirm what he ate."""
    judge, _ = make_judge(puzzle, matches=[match(elements=["scoperta"])])
    question = "Ha capito cosa aveva mangiato?"
    assert puzzle.root not in judge.cards(question, answer("yes", question), [], [])


def test_solution_needs_the_discovery_words(puzzle):
    """Eating the son, without saying he understood it, is not the solution."""
    elements = puzzle.solution_elements
    judge, _ = make_judge(puzzle, matches=[match(elements=["figlio_mangiato"])],
                          stated={elements["figlio_mangiato"]: True})
    question = "Ha mangiato suo figlio?"
    assert puzzle.root not in judge.cards(question, answer("yes", question), [], [])


def test_discovery_is_decided_by_words_alone(puzzle):
    """With the verified element and a discovery word, the solution is won; the verifier never sees the discovery."""
    elements = puzzle.solution_elements
    judge, models = make_judge(puzzle, matches=[match(elements=["figlio_mangiato"])],
                               stated={elements["figlio_mangiato"]: True})
    question = "Al ristorante ha capito di aver mangiato suo figlio"
    assert puzzle.root in judge.cards(question, answer("yes", question), [], [])
    assert not any(elements["scoperta"] in call for call in models.verify_calls)


def test_discovery_word_starts_the_solution_check(puzzle):
    """With a discovery word the solution is checked even when the matcher sees no element."""
    elements = puzzle.solution_elements
    judge, _ = make_judge(puzzle, matches=[match()], stated={elements["figlio_mangiato"]: True})
    question = "Hanno mangiato il figlio morto e lui scoprendolo si è tolto la vita"
    assert puzzle.root in judge.cards(question, answer("yes", question), [], [])


def test_trigger_word_lights_a_door_card_after_yes(puzzle):
    """The stem "ricord" lights the past card after a yes, even when the models propose nothing."""
    judge, models = make_judge(puzzle, matches=[match()])
    question = "Gli ha ricordato qualcosa?"
    assert judge.cards(question, answer("yes", question), [], []) == ["passato"]
    assert models.verify_calls == []


def test_trigger_word_needs_a_yes(puzzle):
    """After a no, the trigger word lights nothing."""
    judge, _ = make_judge(puzzle, matches=[match()])
    question = "Gli ha ricordato qualcosa?"
    assert judge.cards(question, answer("no", question), [], []) == []


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