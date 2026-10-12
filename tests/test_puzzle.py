"""Data checks for every puzzle file: no API calls, safe to run on every push."""
import json
import pytest

from riddle.puzzle import ANSWERS, PUZZLES_DIR, load_arbiter
from riddle.schema import load_riddle

# puzzles with only the arbiter's fields: files named like "arbiter.it.json"
ARBITER_FILES = sorted(PUZZLES_DIR.glob("*/arbiter.*.json"))
# every set of labelled questions, written by hand or simulated: "tests.it.json", "tests.simulated.it.json"
TEST_FILES = sorted(PUZZLES_DIR.glob("*/tests*.json"))


@pytest.mark.parametrize("path", TEST_FILES, ids=str)
def test_test_cases_use_valid_ids(path):
    """Every labelled question uses a known answer and the ids of its riddle's facts and false leads."""
    language = path.name.split(".")[-2]   # "tests.simulated.it.json" -> "it"
    riddle = load_riddle(path.parent.name, language)
    ids = set(riddle.facts) | set(riddle.exclusions)
    for case in json.loads(path.read_text(encoding="utf-8")):
        assert case["answer"] in ANSWERS, case["question"]
        assert set(case["cards"]) <= ids, case["question"]
        assert set(case["lit"]) <= ids, case["question"]


@pytest.mark.parametrize("path", ARBITER_FILES, ids=str)
def test_arbiter_file_loads(path):
    """Every arbiter-only puzzle loads with a story and its solution facts."""
    language = path.name.split(".")[1]   # "arbiter.it.json" -> "it"
    puzzle = load_arbiter(path.parent.name, language)
    assert puzzle.story and puzzle.solution_facts


@pytest.mark.parametrize("path", ARBITER_FILES, ids=str)
def test_arbiter_reads_victory_claims_after_facts(path):
    """The arbiter reads the facts in order of play, then the victory claims, then NOT TRUE."""
    data = json.loads(path.read_text(encoding="utf-8"))
    puzzle = load_arbiter(path.parent.name, path.name.split(".")[1])
    facts = [fact["text"] for fact in data["facts"]]
    claims = [element["claim"] for element in data["victory"]]
    assert puzzle.solution_facts[:-1] == facts + claims
    assert puzzle.solution_facts[-1].startswith("NOT TRUE: ")