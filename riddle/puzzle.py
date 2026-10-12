"""Load what the arbiter reads of a riddle, and the labelled test questions."""

import json
from pathlib import Path
from types import SimpleNamespace

PUZZLES_DIR = Path(__file__).parent.parent / "puzzles"
ANSWERS = ("yes", "no", "irrelevant", "invalid", "unclear")   # the judge's possible answers


def load_tests(name, language, kind=None):
    """Load the labelled test questions from `puzzles/<name>/tests[.<kind>].<language>.json`.

    Args:
        name: Folder name of the puzzle.
        language: Language code of the file.
        kind: Which test set, e.g. "simulated"; None for the main one.

    Returns:
        A list of test cases, each with "group", "question", "answer",
        "cards", "lit" and "history".
    """
    prefix = f"tests.{kind}" if kind else "tests"
    path = PUZZLES_DIR / name / f"{prefix}.{language}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_arbiter(name, language):
    """Load what the arbiter reads from a puzzle written in the card schema.

    The schema has one list of facts, in order of play: they are the solution the
    arbiter judges against. The victory claims follow them, so the arbiter knows
    the conclusion without a duplicate fact. The exclusions become the arbiter's
    "NOT TRUE" line.

    Args:
        name: Folder name of the puzzle, e.g. "baita".
        language: Language code of the file, e.g. "it".

    Returns:
        An object with "title", "story", "solution", "solution_facts", "judge_notes"
        and "card_text" (the text of every fact and false lead, for the ones already lit).
    """
    path = PUZZLES_DIR / name / f"arbiter.{language}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # the facts are the solution: one list, read by the arbiter as it is written
    facts = [fact["text"] for fact in data["facts"]]
    # the victory claims state the conclusion the facts lead to
    claims = [element["claim"] for element in data["victory"]]
    not_true = "NOT TRUE: " + "; ".join(exclusion["text"] for exclusion in data["exclusions"])
    # cards lit in a test reach the arbiter as established facts: their text comes from the schema
    card_text = {item["id"]: item["text"] for item in data["facts"] + data["exclusions"]}
    return SimpleNamespace(title=data["title"], story=data["story"], solution=data["truth"],
                           solution_facts=facts + claims + [not_true], judge_notes=[], card_text=card_text)