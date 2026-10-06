"""Data checks for every puzzle file: no API calls, safe to run on every push."""

import pytest

from riddle.puzzle import ANSWERS, PUZZLES_DIR, load_arbiter, load_puzzle, load_tests
from riddle.schema import load_riddle

# every puzzle in every language: files named like "it.json", "en.json"
PUZZLE_FILES = sorted(PUZZLES_DIR.glob("*/??.json"))
# puzzles with only the arbiter's fields: files named like "arbiter.it.json"
ARBITER_FILES = sorted(PUZZLES_DIR.glob("*/arbiter.*.json"))


@pytest.mark.parametrize("path", PUZZLE_FILES, ids=str)
def test_puzzle_passes_checks(path):
    """Every puzzle loads, so its tree and ids are consistent."""
    load_puzzle(path.parent.name, path.stem)


@pytest.mark.parametrize("path", ARBITER_FILES, ids=str)
def test_test_cases_use_valid_ids(path):
    """Every test case uses a known answer and the ids of the riddle's facts and false leads."""
    language = path.name.split(".")[1]   # "arbiter.it.json" -> "it"
    riddle = load_riddle(path.parent.name, language)
    ids = set(riddle.facts) | set(riddle.exclusions)
    for case in load_tests(path.parent.name, language):
        assert case["answer"] in ANSWERS, case["question"]
        assert set(case["cards"]) <= ids, case["question"]
        assert set(case["lit"]) <= ids, case["question"]


def test_gabbiano_matches_the_notebook():
    """The gabbiano puzzle keeps the numbers validated in the notebook."""
    puzzle = load_puzzle("gabbiano", "it")
    assert len(puzzle.facts) == 21
    assert len(puzzle.deductions) == 9
    assert puzzle.points[puzzle.root] == 550
    assert len(load_tests("gabbiano", "it")) == 154


@pytest.mark.parametrize("path", ARBITER_FILES, ids=str)
def test_arbiter_file_loads(path):
    """Every arbiter-only puzzle loads with a story and its solution facts."""
    language = path.name.split(".")[1]   # "arbiter.it.json" -> "it"
    puzzle = load_arbiter(path.parent.name, language)
    assert puzzle.story and puzzle.solution_facts