"""The state of one game on a riddle in the card schema.

The riddle says what can be found; the session remembers what has been found.
It never judges the player's words: deciding which facts a question states is
the matcher's job. It only remembers which questions were asked, to tell the
conductor when a question is repeated or when the player is going nowhere.
"""

import re
import unicodedata

RELIEF_STREAK = 5   # questions without progress after which a new fact deserves a "finalmente"

def question_key(question):
    """Return the words of a question, so that the same question typed or spoken differently matches.

    Case, accents, apostrophes and punctuation are ignored: "La stufa è accesa?"
    and "la stufa e accesa" have the same key.

    Args:
        question: The question as the arbiter rewrote it.
    """
    text = "".join(c for c in unicodedata.normalize("NFD", question.lower()) if not unicodedata.combining(c))
    return " ".join(re.findall(r"\w+", text.replace("'", " ")))


class Session:
    """One game in progress.

    Attributes:
        riddle: The riddle being played.
        found: Ids of the facts the player has found.
        excluded: Ids of the false leads already closed.
        asked: Keys of the questions asked so far (see `question_key`).
        empty_streak: Questions in a row that found no new fact.
        reached: Whether every fact the victory needs has been found.
    """

    def __init__(self, riddle):
        """Start a game with nothing found.

        Args:
            riddle: A Riddle from riddle.schema.
        """
        self.riddle = riddle
        self.found = set()
        self.excluded = set()
        self.asked = set()
        self.empty_streak = 0
        self.reached = False

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

    def record(self, question, new_facts):
        """Record an answered question and describe the game at this turn, for the conductor.

        Call it after `unlock`, so that the facts this question found already count.

        Args:
            question: The question as the arbiter rewrote it.
            new_facts: Ids of the facts this question found (from `unlock`).

        Returns:
            A dict with "repeated" (the same question was asked before),
            "empty_streak" (questions in a row without a new fact before this one),
            "relief" (a new fact after at least `RELIEF_STREAK` questions without one)
            and "within_reach" (this question found the last fact the victory needs).
        """
        key = question_key(question)
        reached = all(set(element["requires"]) <= self.found for element in self.riddle.victory.values())
        state = {
            "repeated": key in self.asked,
            "empty_streak": self.empty_streak,
            "relief": bool(new_facts) and self.empty_streak >= RELIEF_STREAK,
            # only the turn that completes the victory: the invitation is said once
            "within_reach": reached and not self.reached,
        }
        self.asked.add(key)
        self.reached = reached
        # only a new fact is progress: a closed false lead does not end a streak
        self.empty_streak = 0 if new_facts else self.empty_streak + 1
        return state

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