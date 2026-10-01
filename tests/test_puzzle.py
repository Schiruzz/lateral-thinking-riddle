"""Data checks for every puzzle file: no API calls, safe to run on every push."""

import pytest

from riddle.puzzle import ANSWERS, PUZZLES_DIR, load_puzzle, load_tests

# every puzzle in every language: files named like "it.json", "en.json"
PUZZLE_FILES = sorted(PUZZLES_DIR.glob("*/??.json"))


@pytest.mark.parametrize("path", PUZZLE_FILES, ids=str)
def test_puzzle_passes_checks(path):
    """Every puzzle loads, so its tree and ids are consistent."""
    load_puzzle(path.parent.name, path.stem)


@pytest.mark.parametrize("path", PUZZLE_FILES, ids=str)
def test_test_cases_use_valid_ids(path):
    """Every test case uses a known answer and existing card ids."""
    puzzle = load_puzzle(path.parent.name, path.stem)
    for case in load_tests(path.parent.name, path.stem):
        assert case["answer"] in ANSWERS, case["question"]
        assert set(case["cards"]) <= set(puzzle.card_text), case["question"]
        assert set(case["lit"]) <= set(puzzle.card_text), case["question"]


def test_gabbiano_matches_the_notebook():
    """The gabbiano puzzle keeps the numbers validated in the notebook."""
    puzzle = load_puzzle("gabbiano", "it")
    assert len(puzzle.facts) == 21
    assert len(puzzle.deductions) == 10
    assert puzzle.points[puzzle.root] == 610
    assert len(load_tests("gabbiano", "it")) == 149