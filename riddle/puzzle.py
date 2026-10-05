"""Load lateral thinking puzzles from JSON and check that their data is consistent.

A puzzle is made of fact cards, exclusion cards and a tree of deductions whose
root is the solution. Some deductions are theories: they unlock from a few key
cards instead of their children. Guides are the detective's questions that
lead the player from one card to the next. Every derived table the game and
the judge need (card texts, zones, points, implied cards) is computed here,
once, from the raw data.
"""

import json
from pathlib import Path
from types import SimpleNamespace

PUZZLES_DIR = Path(__file__).parent.parent / "puzzles"
ANSWERS = ("yes", "no", "irrelevant", "invalid", "unclear")   # the judge's possible answers
DEDUCTION_BONUS = 20


class Puzzle:
    """A lateral thinking puzzle with its cards, deduction tree and solution.

    Attributes:
        title: The name of the case, shown to the player.
        story: The text read to the player at the start.
        solution: The full truth as a story, shown to the player at the end.
        solution_facts: The same truth as short facts in time order, shown
            only to the judge's arbiter.
        facts: Fact cards, id -> {"text", "points"}.
        exclusions: Ruled-out false leads, id -> {"text", "points"}.
        prerequisites: Cards each card presupposes, id -> list of ids.
        deductions: Deductions as {"id", "children", "text"}, children before
            parents, root last.
        solution_elements: Key elements the player must state to win, id -> text.
        required_words: Key cards that unlock only if one of these word stems
            appears in the player's words, id -> list of stems.
        trigger_words: Door cards that unlock, with no model, when the answer
            is yes and one of these word stems appears in the player's words,
            id -> list of stems.
        theories: Deductions reachable from key cards instead of their
            children, id -> list of key card ids. The root is one of them.
        guides: Detective questions as {"card", "after", "question"}: the
            question leads to "card" once every card in "after" is lit.
        judge_notes: Puzzle-specific guidance for the judge, e.g. which part
            of the story answers "partly".            
        root: Id of the root deduction, the solution.
        card_text: Text of every card, id -> text.
        card_zone: Zone of every card, id -> "past" or "restaurant".
        implies: Cards each card lights for free, id -> list of ids.
        parent: The deduction that merges each card, id -> deduction id.
        needs: Cards that make each deduction reachable: the key cards of a
            theory, the children of any other deduction.
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
        self.solution_facts = data["solution_facts"]
        self.facts = data["facts"]
        self.exclusions = data["exclusions"]
        self.prerequisites = data["prerequisites"]
        self.deductions = data["deductions"]
        self.solution_elements = data["solution_elements"]
        self.required_words = data["required_words"]
        self.trigger_words = data["trigger_words"]
        self.element_words = data["element_words"]
        self.theories = data["theories"]
        self.guides = data["guides"]
        self.judge_notes = data["judge_notes"]
        self.root = self.deductions[-1]["id"]

        # text of every card, and what each card implies: its prerequisites, or the children of a deduction
        self.card_text = {cid: c["text"] for cid, c in (self.facts | self.exclusions).items()}
        self.card_text |= {d["id"]: d["text"] for d in self.deductions}
        self.implies = dict(self.prerequisites) | {d["id"]: d["children"] for d in self.deductions}
        self.parent = {c: d["id"] for d in self.deductions for c in d["children"]}
        self.needs = {d["id"]: self.theories.get(d["id"], d["children"]) for d in self.deductions}
        # cards listed in the "past" zone stay sealed until the past is opened; all the others are in the restaurant
        self.card_zone = {cid: "past" if cid in data["zones"]["past"] else "restaurant" for cid in self.card_text}
        self.check()

        # in the deductions list each deduction comes after its children, so their points are already known
        self.points = {cid: c["points"] for cid, c in (self.facts | self.exclusions).items()}
        for d in self.deductions:
            self.points[d["id"]] = sum(self.points[c] for c in d["children"]) + DEDUCTION_BONUS

    def check(self):
        """Check that the puzzle data is consistent.

        Raises:
            ValueError: If an id is unknown, a theory is not a deduction, a
                deduction merges cards defined after it, a card is merged
                more than once, or a card cannot be reached from the root.
        """
        # every id used anywhere must be a card
        used = [c for d in self.deductions for c in d["children"]]
        used += [c for cards in self.prerequisites.values() for c in cards]
        used += list(self.prerequisites) + list(self.required_words) + list(self.trigger_words)
        used += [c for keys in self.theories.values() for c in keys]
        used += [c for g in self.guides for c in [g["card"], *g["after"]]]
        unknown = set(used) - set(self.card_text)
        if unknown:
            raise ValueError(f"unknown card ids: {sorted(unknown)}")

        # element words must belong to solution elements
        unknown_elements = set(self.element_words) - set(self.solution_elements)
        if unknown_elements:
            raise ValueError(f"unknown solution element ids: {sorted(unknown_elements)}")

        # theories are deductions with a different unlock rule
        deduction_ids = {d["id"] for d in self.deductions}
        if not set(self.theories) <= deduction_ids:
            raise ValueError(f"theories that are not deductions: {sorted(set(self.theories) - deduction_ids)}")

        # children must be defined before the deduction that merges them
        seen = set(self.facts)
        for d in self.deductions:
            if not set(d["children"]) <= seen:
                raise ValueError(f"{d['id']} merges cards defined after it")
            seen.add(d["id"])

        # a card is merged at most once, so each card has a single place on the board
        merged = [c for d in self.deductions for c in d["children"]]
        if len(merged) != len(set(merged)):
            raise ValueError("a card is merged by more than one deduction")

        # every fact and deduction is lit when the solution is: children and prerequisites, in chain
        if self.closure([self.root]) != set(self.facts) | deduction_ids:
            raise ValueError("some cards cannot be reached from the root")

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

    def is_reachable(self, deduction, lit):
        """Return True if the player can unlock this deduction now.

        A theory is reachable when its key cards are lit; any other deduction
        when its children are lit.

        Args:
            deduction: Id of a deduction.
            lit: Ids of the cards already lit.
        """
        return deduction not in lit and set(self.needs[deduction]) <= set(lit)

    def reachable_deductions(self, lit):
        """Return the deductions the player can unlock now.

        The root is excluded: it is won by stating the solution elements.

        Args:
            lit: Ids of the cards already lit.

        Returns:
            A list of (id, text) pairs.
        """
        return [(d["id"], d["text"]) for d in self.deductions
                if d["id"] != self.root and self.is_reachable(d["id"], lit)]


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
    """Load only what the arbiter reads from `puzzles/<name>/arbiter.<language>.json`.

    Used to test the arbiter on a puzzle that has no cards yet. The card
    sections are left empty: `Judge.__init__` builds the matcher's lists from
    them, and `Judge.answer` reads `card_text` for the cards already lit.

    Args:
        name: Folder name of the puzzle, e.g. "baita".
        language: Language code of the file, e.g. "it".

    Returns:
        An object with the fields of the file ("title", "story", "solution",
        "solution_facts", "judge_notes") and empty card sections.
    """
    path = PUZZLES_DIR / name / f"arbiter.{language}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # no cards: the arbiter never sees them, and nothing can be lit
    return SimpleNamespace(**data, facts={}, exclusions={}, solution_elements={}, card_text={})