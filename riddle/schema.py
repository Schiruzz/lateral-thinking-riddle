"""A riddle written in the card schema: its facts, scenes, exclusions and victory.

Only the structure lives here: what a fact presupposes and which facts can be
found next. The state of a game (what the player has found) lives in the engine.
"""

import json

from riddle.puzzle import PUZZLES_DIR


class Riddle:
    """A riddle in the card schema.

    Attributes:
        id: The riddle's id, e.g. "baita".
        title: The name shown to the player.
        story: The visible situation, read to the player and never rewritten.
        truth: The whole truth as a story, shown at the end.
        facts: Facts by id, in time order (the order of the file).
        scenes: Scenes by id.
        exclusions: False leads by id.
        victory: Victory elements by id.
    """

    def __init__(self, data):
        """Build the riddle from its raw JSON data and check its ids.

        Args:
            data: The parsed content of a riddle file.

        Raises:
            ValueError: If an id points to a fact or scene that does not exist.
        """
        self.id = data["id"]
        self.title = data["title"]
        self.story = data["story"]
        self.truth = data["truth"]
        # dicts keep the order of the file: facts stay in time order
        self.facts = {fact["id"]: fact for fact in data["facts"]}
        self.scenes = {scene["id"]: scene for scene in data["scenes"]}
        self.exclusions = {exclusion["id"]: exclusion for exclusion in data["exclusions"]}
        self.victory = {element["id"]: element for element in data["victory"]}
        self.check()

    def check(self):
        """Check that every id the riddle uses exists, so the engine never meets an unknown one.

        Raises:
            ValueError: If a requires, a ruled_out_by or a scene points nowhere.
        """
        used = [r for fact in self.facts.values() for r in fact["requires"]]
        used += [r for element in self.victory.values() for r in element["requires"]]
        used += [x["ruled_out_by"] for x in self.exclusions.values() if x["ruled_out_by"]]
        unknown = set(used) - set(self.facts)
        if unknown:
            raise ValueError(f"unknown fact ids: {sorted(unknown)}")
        unknown_scenes = {fact["scene"] for fact in self.facts.values()} - set(self.scenes)
        if unknown_scenes:
            raise ValueError(f"unknown scene ids: {sorted(unknown_scenes)}")

    def closure(self, fact_ids):
        """Return the facts together with every fact they presuppose, in chain.

        Finding "Ha mangiato suo figlio" means knowing that the son died: the
        facts a fact requires come with it.

        Args:
            fact_ids: Ids of the starting facts.

        Returns:
            The set of the starting facts and all the facts they presuppose.
        """
        result, queue = set(), list(fact_ids)
        while queue:
            fact_id = queue.pop()
            if fact_id not in result:
                result.add(fact_id)
                queue.extend(self.facts[fact_id]["requires"])
        return result

    def reachable(self, found):
        """Return the facts the player can find next: not found yet, with everything they require found.

        Args:
            found: Ids of the facts already found.

        Returns:
            Fact ids in time order.
        """
        return [fact_id for fact_id, fact in self.facts.items()
                if fact_id not in found and set(fact["requires"]) <= set(found)]


def load_riddle(name, language):
    """Load a riddle from `puzzles/<name>/arbiter.<language>.json`.

    The file keeps its old name until the old card system is gone.

    Args:
        name: Folder name of the riddle, e.g. "baita".
        language: Language code of the file, e.g. "it".

    Returns:
        The checked `Riddle`.
    """
    path = PUZZLES_DIR / name / f"arbiter.{language}.json"
    return Riddle(json.loads(path.read_text(encoding="utf-8")))