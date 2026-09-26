"""Load lateral thinking puzzles from JSON and check that their data is consistent.

A puzzle is made of fact cards, exclusion cards and a tree of deductions whose
root is the solution. Every derived table the game and the judge need (card
texts, points, implied cards) is computed here, once, from the raw data.
"""

import json
from pathlib import Path

PUZZLES_DIR = Path(__file__).parent.parent / "puzzles"
ANSWERS = ("yes", "no", "irrelevant", "invalid", "partly", "unclear")   # the judge's possible answers
DEDUCTION_BONUS = 20


class Puzzle:
    """A lateral thinking puzzle with its cards, deduction tree and solution.

    Attributes:
        title: The name of the case, shown to the player.
        story: The text read to the player at the start.
        solution: The full truth, shown only to the judge.
        facts: Fact cards, id -> {"text", "points"}.
        exclusions: Ruled-out false leads, id -> {"text", "points"}.
        prerequisites: Cards each card presupposes, id -> list of ids.
        deductions: Deductions as {"id", "children", "text"}, children before
            parents, root last.
        solution_elements: Key elements the player must state to win, id -> text.
        required_words: Key cards that unlock only if one of these word stems
            appears in the player's words, id -> list of stems.
        root: Id of the root deduction, the solution.
        card_text: Text of every card, id -> text.
        implies: Cards each card lights for free, id -> list of ids.
        points: Points of every card; a deduction is worth its children plus a bonus.
    """

    def __init__(self, data):
        """Build the puzzle from its raw JSON data and check it.

        Args:
            data: The parsed content of a puzzle JSON file.

        Raises:
            ValueError: If the data is inconsistent (see `check`).
        """
        self.title = data["title"]
        self.story = data["story"]
        self.solution = data["solution"]
        self.facts = data["facts"]
        self.exclusions = data["exclusions"]
        self.prerequisites = data["prerequisites"]
        self.deductions = data["deductions"]
        self.solution_elements = data["solution_elements"]
        self.required_words = data["required_words"]
        self.root = self.deductions[-1]["id"]

        # text of every card, and what each card implies: prerequisites or the two children
        self.card_text = {cid: c["text"] for cid, c in (self.facts | self.exclusions).items()}
        self.card_text |= {d["id"]: d["text"] for d in self.deductions}
        self.implies = dict(self.prerequisites) | {d["id"]: d["children"] for d in self.deductions}
        self.check()

        # in the deductions list each deduction comes after its children, so their points are already known
        self.points = {cid: c["points"] for cid, c in (self.facts | self.exclusions).items()}
        for d in self.deductions:
            self.points[d["id"]] = sum(self.points[c] for c in d["children"]) + DEDUCTION_BONUS

    def check(self):
        """Check that the puzzle data is consistent.

        Raises:
            ValueError: If an id is unknown, a deduction merges cards defined
                after it, or a card is not merged exactly once in the tree.
        """
        # every id used anywhere must be a card
        used = [c for d in self.deductions for c in d["children"]]
        used += [c for cards in self.prerequisites.values() for c in cards]
        used += list(self.prerequisites) + list(self.required_words)
        unknown = set(used) - set(self.card_text)
        if unknown:
            raise ValueError(f"unknown card ids: {sorted(unknown)}")

        # children must be defined before the deduction that merges them
        seen = set(self.facts)
        for d in self.deductions:
            if not set(d["children"]) <= seen:
                raise ValueError(f"{d['id']} merges cards defined after it")
            seen.add(d["id"])

        # every fact and deduction is merged exactly once, except the root
        expected = set(self.facts) | {d["id"] for d in self.deductions if d["id"] != self.root}
        merged = [c for d in self.deductions for c in d["children"]]
        if sorted(merged) != sorted(expected):
            raise ValueError("the deduction tree is broken")

    def closure(self, cards):
        """Return the cards together with every card they imply, in chain.

        Args:
            cards: Ids of the starting cards.

        Returns:
            The set of the starting cards and all the cards they imply.
        """
        result, queue = set(), list(cards)
        while queue:
            card = queue.pop()
            if card not in result:
                result.add(card)
                queue.extend(self.implies.get(card, ()))
        return result

    def reachable_deductions(self, lit):
        """Return the deductions the player can unlock now.

        A deduction is reachable when it is not lit yet and both its children
        are lit. The root is excluded: it is won by stating the solution elements.

        Args:
            lit: Ids of the cards already lit.

        Returns:
            A list of (id, text) pairs.
        """
        return [(d["id"], d["text"]) for d in self.deductions
                if d["id"] != self.root and d["id"] not in lit and set(d["children"]) <= set(lit)]


def load_puzzle(name, language):
    """Load a puzzle from `puzzles/<name>/<language>.json`.

    Args:
        name: Folder name of the puzzle, e.g. "gabbiano".
        language: Language code of the file, e.g. "it".

    Returns:
        The checked `Puzzle`.
    """
    path = PUZZLES_DIR / name / f"{language}.json"
    return Puzzle(json.loads(path.read_text(encoding="utf-8")))


def load_tests(name, language):
    """Load the labelled test questions from `puzzles/<name>/tests.<language>.json`.

    Args:
        name: Folder name of the puzzle.
        language: Language code of the file.

    Returns:
        A list of test cases, each with "group", "question", "answer",
        "cards", "lit" and "history".
    """
    path = PUZZLES_DIR / name / f"tests.{language}.json"
    return json.loads(path.read_text(encoding="utf-8"))