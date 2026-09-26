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