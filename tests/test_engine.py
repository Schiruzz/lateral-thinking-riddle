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


def test_the_same_question_written_differently_is_repeated(baita):
    assert not baita.record("La stufa è accesa?", [])["repeated"]
    assert baita.record("la stufa e' accesa", [])["repeated"]


def test_empty_streak_counts_questions_without_new_facts(baita):
    for question in ["Era vecchio?", "Era ricco?", "Era alto?"]:
        baita.record(question, [])
    assert baita.record("C'era una stufa?", baita.unlock(["stufa"]))["empty_streak"] == 3
    assert baita.record("Era accesa?", [])["empty_streak"] == 0


def test_victory_is_within_reach_once_when_its_facts_are_found(baita):
    assert not baita.record("C'era una stufa?", baita.unlock(["stufa"]))["within_reach"]
    new = baita.unlock(["gas", "comignolo"])
    assert baita.record("La neve ha bloccato il comignolo e il gas l'ha ucciso?", new)["within_reach"]
    assert not baita.record("Era notte?", [])["within_reach"]


def test_relief_needs_a_new_fact_after_a_long_streak(baita):
    for question in ["Era vecchio?", "Era ricco?", "Era alto?", "Era biondo?", "Era stanco?"]:
        assert not baita.record(question, [], "no")["relief"]
    assert not baita.record("Nevicava?", [], "yes")["relief"]
    assert baita.record("C'era una stufa?", baita.unlock(["stufa"]), "yes")["relief"]


def test_relief_never_comes_with_a_no(baita):
    for n in range(1, 6):
        baita.record(f"Domanda {n}?", [], "no")
    assert not baita.record("Mancava la stufa?", baita.unlock(["stufa"]), "no")["relief"]


def test_the_player_is_told_he_is_stuck_once_every_five_questions(baita):
    stuck = [baita.record(f"Domanda {n}?", [], "no")["stuck"] for n in range(1, 11)]
    assert stuck == [False] * 4 + [True] + [False] * 4 + [True]


def test_the_player_is_never_told_he_is_stuck_after_a_yes(baita):
    for n in range(1, 5):
        baita.record(f"Domanda {n}?", [], "no")
    assert not baita.record("Nevicava?", [], "yes")["stuck"]
    assert baita.record("Domanda 6?", [], "no")["stuck"]


def test_a_sentence_with_every_element_wins(gabbiano):
    assert gabbiano.record("Tutta la storia?", [], "yes", ["v_figlio", "v_inganno", "v_cieco"])["victory"]


def test_part_of_the_explanation_asks_the_why_of_the_next_element_once(gabbiano):
    assert gabbiano.record("Ha mangiato suo figlio?", [], "yes", ["v_figlio"])["relaunch"] == "v_inganno"
    assert gabbiano.record("Ha mangiato il figlio sull'isola?", [], "yes", ["v_figlio"])["relaunch"] is None
    assert gabbiano.record("La moglie gli ha detto che era gabbiano?", [], "yes", ["v_inganno"])["relaunch"] == "v_cieco"


def test_a_no_to_an_explanation_has_a_wrong_part(gabbiano):
    state = gabbiano.record("Ha mangiato il figlio e lo sapeva?", [], "no", ["v_figlio"])
    assert state["wrong_part"] and not state["victory"] and state["relaunch"] is None


def test_every_element_in_different_sentences_asks_for_the_whole_story_once(gabbiano):
    gabbiano.record("Ha mangiato suo figlio?", [], "yes", ["v_figlio"])
    gabbiano.record("La moglie gli ha detto che era gabbiano?", [], "yes", ["v_inganno"])
    assert gabbiano.record("Era cieco?", [], "yes", ["v_cieco"])["summary"]
    assert not gabbiano.record("Era proprio cieco?", [], "yes", ["v_cieco"])["summary"]


def test_a_no_with_a_new_victory_element_says_part_is_true_once(gabbiano):
    assert gabbiano.record("Ha mangiato il figlio e lo sapeva?", [], "no", ["v_figlio"])["wrong_part"]
    assert not gabbiano.record("Ha mangiato il figlio crudo?", [], "no", ["v_figlio"])["wrong_part"]