"""A riddle written in the card schema: its facts, scenes, exclusions and victory.

Only the structure lives here: what a fact presupposes and which facts can be
found next. The state of a game (what the player has found) lives in the engine.
"""

import json

from riddle.puzzle import PUZZLES_DIR


def by_id(items, kind):
    """Index items by their id, refusing duplicates.

    Args:
        items: A list of dicts, each with an "id" key.
        kind: What the items are, used in the error message (e.g. "fact").

    Returns:
        A dict from id to item, in the order of the list.

    Raises:
        ValueError: If two items share an id.
    """
    ids = [item["id"] for item in items]
    # a plain dict would silently keep only the last item with a repeated id
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate {kind} ids: {duplicates}")
    return {item["id"]: item for item in items}


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
          ValueError: If two items share an id, or an id points to a fact or
              scene that does not exist.
        """
        self.id = data["id"]
        self.title = data["title"]
        self.story = data["story"]
        self.truth = data["truth"]
        # dicts keep the order of the file: facts stay in time order
        self.facts = by_id(data["facts"], "fact")
        self.scenes = by_id(data["scenes"], "scene")
        self.exclusions = by_id(data["exclusions"], "exclusion")
        self.victory = by_id(data["victory"], "victory")
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



def by_id(items, kind):
    """Index items by id, refusing duplicates (a dict would silently keep the last)."""
    ids = [item["id"] for item in items]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate {kind} ids: {duplicates}")
    return {item["id"]: item for item in items}