"""Checks of the card schema's structure: no API calls, safe to run on every push."""

import pytest
from riddle.schema import Riddle, load_riddle, by_id


@pytest.fixture
def baita():
    """The cabin riddle."""
    return load_riddle("baita", "it")


@pytest.fixture
def gabbiano():
    """The seagull riddle."""
    return load_riddle("gabbiano", "it")


def test_riddles_load(baita, gabbiano):
    """Both riddles load and keep their facts in the order of the file."""
    assert list(baita.facts)[0] == "solo_cinque"
    assert list(gabbiano.facts)[0] == "passato"


def test_closure_brings_what_a_fact_presupposes(gabbiano):
    """Knowing he ate his son means knowing the son died, and everything that presupposes."""
    assert gabbiano.closure(["mangiato_figlio"]) == {
        "mangiato_figlio", "carne_umana", "figlio_morto", "figlio", "terza_persona", "passato"}


def test_reachable_at_start_has_only_facts_without_requires(baita):
    """At the start, only facts that require nothing can be found."""
    reachable = baita.reachable(set())
    assert "gas" in reachable and "stufa" in reachable
    assert "stufa_carica" not in reachable


def test_reachable_opens_after_a_fact_is_found(baita):
    """Finding the stove makes the facts about the stove reachable."""
    reachable = baita.reachable({"stufa"})
    assert "stufa_carica" in reachable and "comignolo" in reachable
    assert "stufa" not in reachable


def test_unknown_requires_is_rejected():
    """A fact that requires a fact that does not exist is an authoring mistake."""
    data = {"id": "x", "title": "x", "story": "x", "truth": "x",
            "scenes": [{"id": "s", "name": "s", "sealed": False}],
            "facts": [{"id": "a", "text": "a", "scene": "s", "role": "P", "requires": ["missing"]}],
            "exclusions": [], "victory": []}
    with pytest.raises(ValueError, match="missing"):
        Riddle(data)


def test_duplicate_ids_are_refused():
    with pytest.raises(ValueError, match="duplicate exclusion ids"):
        by_id([{"id": "veleno_cibo"}, {"id": "veleno_cibo"}], "exclusion")


def test_detective_counts_needed_facts_plus_half():
    assert load_riddle("baita", "it").detective() == 5
    assert load_riddle("gabbiano", "it").detective() == 20


def test_key_facts_are_leaps_twists_and_what_presupposes_them(baita, gabbiano):
    """The verifier protects leaps and twists, and the facts that would bring one along."""
    assert baita.key_facts == {"gas", "monossido", "comignolo", "gas_intrappolato"}
    assert gabbiano.key_facts == {"cieco", "mangiato_figlio", "gabbiano_creduto", "sapore"}