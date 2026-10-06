import pytest

from riddle.engine import Session
from riddle.schema import load_riddle


@pytest.fixture
def baita():
    return Session(load_riddle("baita", "it"))


@pytest.fixture
def gabbiano():
    return Session(load_riddle("gabbiano", "it"))


def test_a_new_game_has_nothing_found_and_only_open_scenes(baita):
    assert baita.found == set()
    assert baita.open_scenes() == ["mattina"]


def test_unlock_adds_the_presupposed_facts_in_time_order(baita):
    assert baita.unlock(["comignolo"]) == ["stufa", "comignolo"]


def test_unlock_returns_only_new_facts(baita):
    baita.unlock(["stufa"])
    assert baita.unlock(["comignolo"]) == ["comignolo"]


def test_a_sealed_scene_opens_with_its_first_fact(gabbiano):
    assert "anni_prima" not in gabbiano.open_scenes()
    gabbiano.unlock(["isola"])
    assert "anni_prima" in gabbiano.open_scenes()


def test_found_fact_closes_the_false_leads_it_rules_out(baita):
    baita.unlock(["gas"])
    assert {"veleno_cibo", "freddo"} <= baita.excluded
    # ruled out by another fact, so it stays open
    assert "amico_colpevole" not in baita.excluded


def test_exclude_closes_a_lead_without_finding_facts(baita):
    baita.exclude(["passaggio"])
    assert baita.excluded == {"passaggio"}
    assert baita.found == set()


def test_reachable_follows_what_was_found(baita):
    assert "stufa_carica" not in baita.reachable()
    baita.unlock(["stufa"])
    assert "stufa_carica" in baita.reachable()