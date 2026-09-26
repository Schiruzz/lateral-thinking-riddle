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
    assert new == ["figlio_morto", "figlio", "terza_persona"]
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
    game.unlock(["moglie", "terza_persona"])
    assert game.board()["cards"] == ["moglie", "terza_persona"]
    game.unlock(["d_non_soli"])
    assert game.board()["cards"] == ["d_non_soli"]


def test_board_keeps_ruled_out_leads_apart(game):
    """Exclusions are listed apart and never take a place among the cards."""
    game.unlock(["carne_ok", "moglie"])
    assert game.board() == {"cards": ["moglie"], "ruled_out": ["carne_ok"]}


def test_board_shrinks_to_the_solution(game):
    """Once the solution is lit, it is the only card left on the board."""
    game.unlock([game.puzzle.root])
    assert game.board()["cards"] == [game.puzzle.root]