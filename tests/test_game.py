"""Game logic checks on the gabbiano puzzle: no API calls, safe to run on every push."""

import pytest

from riddle.game import Game
from riddle.puzzle import load_puzzle


@pytest.fixture
def game():
    """A fresh game of the gabbiano puzzle."""
    return Game(load_puzzle("gabbiano", "it"))


def test_prerequisites_are_lit_for_free(game):
    """A fact lights its prerequisites in chain, but only the fact scores."""
    new = game.unlock(["figlio_morto"])
    assert new == ["figlio_morto", "figlio", "passato", "terza_persona"]
    assert game.score == game.puzzle.points["figlio_morto"]


def test_deduction_lights_its_children_for_free(game):
    """A deduction lights its children and their prerequisites, and only the deduction scores."""
    game.unlock(["d_pieta"])
    assert {"d_pieta", "bugia", "motivo", "moglie"} <= set(game.lit)
    assert game.score == game.puzzle.points["d_pieta"]


def test_card_already_lit_scores_nothing(game):
    """Unlocking a lit card again adds no card and no points."""
    game.unlock(["moglie"])
    assert game.unlock(["moglie"]) == []
    assert game.score == game.puzzle.points["moglie"]


def test_solution_wins_and_lights_the_whole_tree(game):
    """Stating the solution wins and reveals every fact and deduction as explanation."""
    game.unlock([game.puzzle.root])
    assert game.won()
    assert len(game.lit) == len(game.puzzle.facts) + len(game.puzzle.deductions)
    assert game.score == game.puzzle.points[game.puzzle.root]


def test_board_hides_cards_merged_into_a_deduction(game):
    """Two cards are shown until the player links them, then only their deduction is."""
    game.unlock(["verifica", "mai_gabbiano"])
    assert game.board()["cards"] == ["verifica", "mai_gabbiano"]
    game.unlock(["d_verifica"])
    assert game.board()["cards"] == ["d_verifica"]


def test_board_keeps_ruled_out_leads_apart(game):
    """Exclusions are listed apart and never take a place among the cards."""
    game.unlock(["carne_ok", "moglie"])
    board = game.board()
    assert board["cards"] == ["moglie"]
    assert board["ruled_out"] == ["carne_ok"]


def test_board_shrinks_to_the_solution(game):
    """Once the solution is lit, it is the only card left on the board."""
    game.unlock([game.puzzle.root])
    assert game.board()["cards"] == [game.puzzle.root]


def test_card_nobody_merges_leaves_when_presupposed(game):
    """The other person leaves the board once we know it is the son."""
    game.unlock(["terza_persona"])
    assert game.board()["cards"] == ["terza_persona"]
    game.unlock(["figlio"])
    assert game.board()["cards"] == ["figlio"]


def test_past_opens_with_its_first_card(game):
    """The past is sealed at the start and opens with any of its facts, lighting the past card too."""
    assert not game.board()["past_open"]
    game.unlock(["naufragio"])
    assert game.board()["past_open"]


def test_past_lead_waits_for_the_past(game):
    """A ruled-out lead of the past stays hidden while the past is sealed."""
    game.unlock(["nessun_omicidio"])
    board = game.board()
    assert not board["past_open"] and board["ruled_out"] == []
    game.unlock(["passato"])
    assert game.board()["ruled_out"] == ["nessun_omicidio"]


def test_first_guides_at_the_start(game):
    """Before any question, the board asks about the gull and the woman."""
    assert [g["card"] for g in game.board()["guides"]] == ["verifica", "moglie"]


def test_thread_links_the_children_of_a_deduction(game):
    """Once both children are lit, a thread without a question links them."""
    game.unlock(["verifica", "mai_gabbiano"])
    thread = game.board()["threads"][0]
    assert thread["id"] == "d_verifica"
    assert thread["cards"] == ["verifica", "mai_gabbiano"]
    assert not thread["theory"] and thread["question"] is None


def test_secondary_with_its_own_cards_keeps_its_thread(game):
    """The son-on-the-island secondary also needs the food card, so it keeps its thread beside the tragedy's."""
    game.unlock(["naufragio", "isola", "fame", "figlio_morto"])
    ids = [t["id"] for t in game.board()["threads"]]
    assert "d_tragedia" in ids and "d_figlio_isola" in ids


def test_final_thread_before_the_solution(game):
    """With the meal and the deception lit, the root's thread asks the final question."""
    game.unlock(["t_pasto", "d_inganno"])
    thread = next(t for t in game.board()["threads"] if t["id"] == game.puzzle.root)
    assert thread["question"] == "Allora: cosa ha capito al ristorante?"


def test_intermediate_cards_give_way_to_the_shipwreck(game):
    """Incident, sea and boat show one at a time, and all leave the board once the shipwreck is found."""
    game.unlock(["incidente"])
    assert "incidente" in game.board()["cards"]
    game.unlock(["mare"])
    assert "incidente" not in game.board()["cards"] and "mare" in game.board()["cards"]
    game.unlock(["naufragio"])
    assert not {"incidente", "mare", "barca"} & set(game.board()["cards"])