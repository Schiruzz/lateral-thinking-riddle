"""The state of one game on a riddle in the card schema.

The riddle says what can be found; the session remembers what has been found.
It never judges the player's words: deciding which facts a question states is
the matcher's job. It only remembers which questions were asked, to tell the
conductor when a question is repeated or when the player is going nowhere.
"""

import re
import unicodedata

RELIEF_STREAK = 5   # questions without progress after which a new fact deserves a "finalmente"
STUCK_STREAK = 5    # questions in a row without progress after which the player is going nowhere
SCENE_STALL = 3   # stalls in a row before the sealed scene the player has not entered is named
GIFT_STALL = 3    # stalls in a row, in the final phase, before the next fact is given away

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
        stuck_from: The streak at which the conductor last said the player was stuck.
        reached: Whether every fact the victory needs has been found.
        claimed: Ids of the victory elements the player has explained so far, in any sentence.
        relaunched: Ids of the victory elements whose "why" was already asked.
        summary_asked: Whether the player was already asked to tell the whole story.
        partly_told: Ids of the victory elements a "no" already said were true.   
        stalls: Stalls in a row since the player last found a fact by himself.
        scenes_hinted: Ids of the sealed scenes already named as a hint.     
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
        self.stuck_from = 0
        self.reached = False
        self.claimed = set()
        self.relaunched = set()
        self.summary_asked = False
        self.partly_told = set()       
        self.stalls = 0
        self.scenes_hinted = set() 

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

    def record(self, question, new_facts, answer="", stated=()):
        """Record an answered question and describe the game at this turn, for the conductor.

        Call it after `unlock`, so that the facts this question found already count.

        Args:
            question: The question as the arbiter rewrote it.
            new_facts: Ids of the facts this question found (from `unlock`).
            answer: The arbiter's answer: relief comes only with a yes, after a yes the
                player is never told he is stuck, and invalid or unclear sentences do not
                count for a stall.
            stated: Ids of the victory elements the sentence puts forward (from
                `Matcher.stated_victory`).

        Returns:
            A dict with "repeated" (the same question was asked before),
            "empty_streak" (questions in a row without a new fact before this one),
            "relief" (a yes that found a new fact after at least `RELIEF_STREAK`
            questions without one),
            "stuck" (`STUCK_STREAK` more questions without a new fact since the last time
            it was said, never after a yes),
            "within_reach" (this question found the last fact the victory needs),
            "victory" (a yes to a sentence with every victory element),
            "relaunch" (the victory element whose "why" to ask now, or None),
            "summary" (every element explained, never in one sentence: ask for the whole story),
            "wrong_part" (a no to a sentence with a victory element not explained yet, or with all of them),
            "hint" (on a stuck turn: "scene", "reconnect", "gift" or None),
            "hint_target" (the id of that scene, victory element or fact)
            and "given" (the facts a gift unlocked).
        """
        key = question_key(question)
        # an element counts as explained only once the facts it needs are found: otherwise the "why" of the
        # next one would name them; the victory takes the matcher's judgement as it is
        explained = [element_id for element_id in stated
                     if set(self.riddle.victory[element_id]["requires"]) <= self.found] if answer == "yes" else []
        reached = all(set(element["requires"]) <= self.found for element in self.riddle.victory.values())
        # invalid and unclear sentences are not questions about the story: they leave the streak as it is
        counted = answer not in ("invalid", "unclear")
        streak = (0 if new_facts else self.empty_streak + 1) if counted else self.empty_streak
        if answer == "yes":
            # what the player has explained so far, sentence after sentence: it picks the next "why"
            self.claimed |= set(explained)
        missing = [element_id for element_id in self.riddle.victory if element_id not in self.claimed]
        victory = answer == "yes" and set(stated) == set(self.riddle.victory)
        # a no to a sentence with victory elements: part of it is true (what partly used to say), but only for
        # elements not explained or told yet, so narrowing questions on a known element get a plain no;
        # a whole explanation with a wrong part is always told
        new_parts = set(stated) - self.claimed - self.partly_told if answer == "no" else set()
        whole = answer == "no" and set(stated) == set(self.riddle.victory)
        # said once per STUCK_STREAK questions, so it does not become a sermon at every turn
        stuck = counted and streak - self.stuck_from >= STUCK_STREAK and answer != "yes"
        if new_facts:
            self.stalls = 0   # a fact found by the player ends the stalls in a row
        hint, target, given = None, None, []
        if stuck:
            self.stalls += 1
            hint, target = self._hint(missing)
            if hint == "gift":
                given = self.unlock([target])   # a gift is found like any fact
            elif hint == "scene":
                self.scenes_hinted.add(target)
        state = {
            "repeated": key in self.asked,
            "empty_streak": self.empty_streak,
            # a "no" can find a fact too, but "Finalmente!" before a no sounds like a yes
            "relief": bool(new_facts) and self.empty_streak >= RELIEF_STREAK and answer == "yes",
            "stuck": stuck,
            # only the turn that completes the victory: the invitation is said once
            "within_reach": reached and not self.reached,
            "victory": victory,
            # after a yes that explains part of the story, the "why" of the next element in the
            # reasoning, asked once: the elements are in the order the reasoning follows
            "relaunch": (missing[0] if answer == "yes" and explained and missing
                         and missing[0] not in self.relaunched else None),
            # every element explained, but never all in one sentence: the whole story, asked once
            "summary": answer == "yes" and bool(explained) and not missing and not victory and not self.summary_asked,
            "wrong_part": bool(new_parts) or whole,
            "hint": hint,
            "hint_target": target,
            "given": given,
        }
        self.asked.add(key)
        self.reached = reached
        # only a new fact is progress: a closed false lead does not end a streak
        self.empty_streak = streak
        self.stuck_from = streak if stuck else (0 if new_facts else self.stuck_from)
        if state["relaunch"]:
            self.relaunched.add(state["relaunch"])
        self.summary_asked = self.summary_asked or state["summary"]
        self.partly_told |= new_parts
        return state


    def _hint(self, missing):
        """Choose the help for a stall: what kind, and about what.

        Before the player explains any victory element, only the sealed scene he has not
        entered, once, from the `SCENE_STALL`-th stall in a row. In the final phase, the
        open "why" again, then, from the `GIFT_STALL`-th stall in a row, the next fact the
        missing element needs: given away only at the end, after the player's reasoning.

        Args:
            missing: Ids of the victory elements not explained yet, in reasoning order.

        Returns:
            A pair: "scene", "reconnect", "gift" or None, and the id of its scene, victory
            element or fact.
        """
        if self.claimed and missing:
            if self.stalls < GIFT_STALL:
                return "reconnect", missing[0]
            needed = self.riddle.closure(self.riddle.victory[missing[0]]["requires"]) - self.found
            gifts = [fact_id for fact_id in self.reachable() if fact_id in needed]
            return ("gift", gifts[0]) if gifts else ("reconnect", missing[0])
        if self.stalls >= SCENE_STALL:
            hidden = [scene_id for scene_id, scene in self.riddle.scenes.items()
                      if scene["sealed"] and scene_id not in self.open_scenes() and scene_id not in self.scenes_hinted]
            if hidden:
                return "scene", hidden[0]
        return None, None
    

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