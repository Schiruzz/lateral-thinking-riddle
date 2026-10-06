"""The state of one game on a riddle in the card schema.

The riddle says what can be found; the session remembers what has been found.
It never reads the player's words: deciding which facts a question states is
the matcher's job.
"""


class Session:
    """One game in progress.

    Attributes:
        riddle: The riddle being played.
        found: Ids of the facts the player has found.
        excluded: Ids of the false leads already closed.
    """

    def __init__(self, riddle):
        """Start a game with nothing found.

        Args:
            riddle: A Riddle from riddle.schema.
        """
        self.riddle = riddle
        self.found = set()
        self.excluded = set()

    def unlock(self, fact_ids):
        """Mark facts as found, together with everything they presuppose.

        Args:
            fact_ids: Ids of the facts the player has just stated.

        Returns:
            The ids of the newly found facts, in time order.
        """
        new = self.riddle.closure(fact_ids) - self.found
        self.found |= new
        # a false lead closes as soon as the fact that rules it out is found
        self.excluded |= {
            exclusion_id
            for exclusion_id, exclusion in self.riddle.exclusions.items()
            if exclusion["ruled_out_by"] in self.found
        }
        return [fact_id for fact_id in self.riddle.facts if fact_id in new]

    def exclude(self, exclusion_ids):
        """Close false leads the player has asked about.

        Args:
            exclusion_ids: Ids of the false leads to close.
        """
        self.excluded |= set(exclusion_ids)

    def open_scenes(self):
        """List the scenes shown on the board.

        Returns:
            Scene ids in file order: the open ones, plus the sealed ones
            where at least one fact has been found.
        """
        scenes_found = {self.riddle.facts[fact_id]["scene"] for fact_id in self.found}
        return [
            scene_id
            for scene_id, scene in self.riddle.scenes.items()
            if not scene["sealed"] or scene_id in scenes_found
        ]

    def reachable(self):
        """List the facts that can be found next.

        Returns:
            Ids of the facts not yet found whose presupposed facts are all found.
        """
        return self.riddle.reachable(self.found)