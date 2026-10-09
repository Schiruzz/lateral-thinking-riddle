"""One game on a riddle: the whole chain that turns a question into the sentence the player hears.

The server and the evaluation run the same turn, so what is measured is what is played.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from riddle.conductor import Conductor
from riddle.engine import Session, question_key
from riddle.judge import JUDGE_MODEL, MAX_ATTEMPTS, UNCLEAR, Judge, Matcher
from riddle.puzzle import load_arbiter
from riddle.schema import load_riddle


# the answers to the offer of a hint, checked in code before the arbiter: "sì" is not a question about the story
ACCEPT = ("si", "ok", "okay", "certo", "dai", "volentieri", "grazie", "va bene", "per favore", "magari", "perche no")
DECLINE = ("no", "niente", "non ancora", "lascia stare", "meglio di no")
OFFER_ANSWER_WORDS = 4   # a longer sentence is a question, not an answer to the offer


def offer_answer(text):
    """Tell whether the player's words answer the offer of a hint.

    Args:
        text: The player's words.

    Returns:
        True for a yes, False for a no, None for anything else: a question lets the offer lapse.
    """
    key = question_key(text)
    words = key.split()
    if not words or len(words) > OFFER_ANSWER_WORDS:
        return None
    if words[0] == "no" or key in DECLINE:
        return False
    if any(f" {phrase} " in f" {key} " for phrase in ACCEPT):
        return True
    return None


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
        finished: Whether the riddle was solved: no more questions after that.
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
        self.finished = False        

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
        if self.session.offer:
            accepted = offer_answer(question)
            if accepted is not None:
                return self.answer_offer(question, accepted)
        start = time.perf_counter()
        verdict = self.chain["judge"].answer(question, self.history, sorted(self.session.found))
        judged = time.perf_counter()
        # the victory check needs only the verdict: beside the matcher, the player waits no longer
        with ThreadPoolExecutor(max_workers=2) as pool:
            matching = pool.submit(self.chain["matcher"].match, question, verdict, self.history, self.session)
            claiming = pool.submit(self.chain["matcher"].stated_victory, verdict, self.history, self.session)
            facts, leads = matching.result()
            stated = claiming.result()

        matched = time.perf_counter()
        new = self.session.unlock(facts)
        self.session.exclude(leads)
        state = self.session.record(verdict["positive_question"], new, verdict["answer"], stated)
        new = new + state["given"]   # a fact given away is found too: the notebook shows it
        said = self.chain["conductor"].reply(question, verdict, self.history, self.session, new, state, self.said)
        end = time.perf_counter()

        self.said.append(said["reply"])

        # an answer not understood is not an exchange: the player asks again, as in the game
        if verdict["answer"] != UNCLEAR:
            self.history.append((verdict["positive_question"], verdict["answer"]))

        self.finished = state["victory"]

        return {"question": question, "positive_question": verdict["positive_question"],
                "answer": verdict["answer"], "new": new, "stated": stated, **state, **said,
                "seconds": end - start, "arbiter_seconds": judged - start,
                "matcher_seconds": matched - judged, "conductor_seconds": end - matched}


    def answer_offer(self, question, accepted):
        """Answer the player's yes or no to the offer of a hint, without the arbiter: it is not a question.

        Args:
            question: The player's words.
            accepted: Whether they said yes.

        Returns:
            A dict with the keys of `ask`; "answer" is "accepted" or "declined".
        """
        start = time.perf_counter()
        state = self.session.answer_offer(accepted)
        said = self.chain["conductor"].offer_reply(state, self.history, self.session, self.said)
        end = time.perf_counter()
        self.said.append(said["reply"])
        return {"question": question, "positive_question": question, "answer": "accepted" if accepted else "declined",
                "new": state["given"], "stated": [], **state, **said,
                "seconds": end - start, "arbiter_seconds": 0.0, "matcher_seconds": 0.0, "conductor_seconds": end - start}