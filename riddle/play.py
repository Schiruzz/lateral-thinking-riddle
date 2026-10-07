"""One game on a riddle: the whole chain that turns a question into the sentence the player hears.

The server and the evaluation run the same turn, so what is measured is what is played.
"""

import time

from riddle.conductor import Conductor
from riddle.engine import Session
from riddle.judge import JUDGE_MODEL, MAX_ATTEMPTS, UNCLEAR, Judge, Matcher
from riddle.puzzle import load_arbiter
from riddle.schema import load_riddle


def load_chain(name, language, client, model=JUDGE_MODEL, max_attempts=MAX_ATTEMPTS):
    """Load the components that answer a question on one riddle, shared by every game on it.

    Args:
        name: The riddle's folder under puzzles/.
        language: The language of the riddle file, e.g. "it".
        client: A `genai.Client`, shared by every component.
        model: The model of the arbiter and the matcher.
        max_attempts: Calls per request: low in a live game, where a player is waiting.

    Returns:
        A dict with "riddle", "judge", "matcher" and "conductor".
    """
    riddle = load_riddle(name, language)
    return {"riddle": riddle,
            "judge": Judge(load_arbiter(name, language), client, model, max_attempts=max_attempts),
            "matcher": Matcher(riddle, client, model, max_attempts=max_attempts),
            "conductor": Conductor(riddle, client, max_attempts=max_attempts)}


class Play:
    """One game on a riddle, turn by turn.

    Attributes:
        chain: The components from `load_chain`.
        session: The engine's state of the game.
        history: (positive question, answer) pairs so far, read by every component.
        said: The sentences the player has heard, so the conductor's banks never repeat.
    """

    def __init__(self, chain):
        """Start a game with nothing found.

        Args:
            chain: The components from `load_chain`.
        """
        self.chain = chain
        self.session = Session(chain["riddle"])
        self.history = []
        self.said = []

    def ask(self, question):
        """Answer one question through the whole chain and update the game.

        Args:
            question: The player's words.

        Returns:
            A dict with "question", the arbiter's "positive_question" and "answer",
            "new" (the facts found), the engine's state (see `Session.record`), the
            conductor's result (see `Conductor.reply`) and the seconds of the whole turn
            and of each component, the time the player waits.
        """
        start = time.perf_counter()
        verdict = self.chain["judge"].answer(question, self.history, sorted(self.session.found))
        judged = time.perf_counter()
        facts, leads = self.chain["matcher"].match(question, verdict, self.history, self.session)
        matched = time.perf_counter()
        new = self.session.unlock(facts)
        self.session.exclude(leads)
        state = self.session.record(verdict["positive_question"], new, verdict["answer"])
        said = self.chain["conductor"].reply(question, verdict, self.history, self.session, new, state, self.said)
        end = time.perf_counter()

        self.said.append(said["reply"])
        # an answer not understood is not an exchange: the player asks again, as in the game
        if verdict["answer"] != UNCLEAR:
            self.history.append((verdict["positive_question"], verdict["answer"]))
        return {"question": question, "positive_question": verdict["positive_question"],
                "answer": verdict["answer"], "new": new, **state, **said,
                "seconds": end - start, "arbiter_seconds": judged - start,
                "matcher_seconds": matched - judged, "conductor_seconds": end - matched}