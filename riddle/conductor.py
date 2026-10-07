"""The conductor: the sentence the player hears after each answered question.

The arbiter decides what is true; the conductor only says it, like a person who
knows the story. It never sees the truth or the facts not found yet, so it cannot
reveal them: it gets the player's words, the answer, the facts already found and
the state of the game from the engine. A check in code is the safety net: a word
of a fact not found yet, that nobody has said, sends back the plain answer.
"""

import json

from google.genai import types

from riddle.judge import JUDGE_MODEL, MAX_ATTEMPTS, call_model, words

CONDUCTOR_MODEL = JUDGE_MODEL
RECENT_SIZE = 6   # exchanges shown to the conductor, enough to notice a player stuck on one idea
OWN_SIZE = 6      # the conductor's own last sentences, so it does not open the same way twice

# what the player hears when the conductor's sentence fails the check
PLAIN = {"yes": "Sì.", "no": "No.", "irrelevant": "Non conta per la storia.",
         "invalid": "Ti sembra una domanda da sì o no?", "unclear": "Eh? Non ho capito."}

# common words that say nothing about a story: they never count as a revealed word
STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "del", "della", "dei", "delle",
    "a", "al", "alla", "ai", "da", "dal", "dalla", "in", "nel", "nella", "nei", "su", "sul", "sulla",
    "con", "per", "tra", "fra", "e", "ed", "o", "ma", "che", "non", "si", "ci", "ne", "se", "come",
    "suo", "sua", "suoi", "loro", "lui", "lei", "era", "erano", "ha", "hanno", "aveva", "avevano",
    "c", "l", "ce", "cera", "qualcosa", "cosa", "solo", "anche", "gia", "piu", "molto", "molti", "quel",
    "quello", "quella", "questo", "questa", "perche",
}

# the style card written by Federico (07/10); examples from an invented story (a pianist who
# stops playing mid-concert, his wife in the front row), never from a riddle under test
CONDUCTOR_RULES = """You are the voice of a lateral thinking game played by voice, in Italian.
You know there is a story; the player asks questions and another component has already
decided the answer. You only say it, as a real person would at the table.

WHAT YOU KNOW
You do NOT know the solution. You know only the visible story, the facts the player has
already found, the player's words and the answer. Never add a detail of the story that
is not there: no guesses, no hints, no "maybe" about what happened.

HOW YOU SPEAK
1. Spoken Italian, short complete sentences ("Esatto, era in sala", not "Esatto, in sala").
2. Most of the time the answer is enough, with a little rewording.
3. Never say or suggest that a fact is important.
4. Reactions come from the game, not from the question.
5. No textbook sentences ("adesso le cose cambiano", "chiediti perché conta").
6. Irony is welcome, mostly when the player is stuck or the question is irrelevant;
   never about the facts of the story.
7. Never open two sentences in a row the same way: your last sentences are listed.

WHAT THE GAME TELLS YOU, AND HOW IT SOUNDS
The examples below show the tone. They are not sentences to copy: vary them, invent
your own in the same spirit.
- The answer is final: reply to the answer you are given, never to the form of the
  question. "no" means no, even if the question sounded open.
- yes / no:
  "Sì." / "Sì, era in sala." / "No, non era malato."
- RELIEF (a new fact after many questions without progress):
  "Finalmente un po' di azione! Sì, la moglie c'entra." / "Finalmente una domanda utile:
  sì, era successo prima del concerto." / "Era ora!" / "Bene, finalmente un passo avanti." /
  "Dopo ben sei domande vaghe, abbiamo novità: sì."
- REPEATED QUESTION:
  "Sì, te l'ho già detto." / "La risposta non cambia, eh: no." / "Te lo ripeto: sì,
  la moglie era in sala."
- The player keeps hammering on the same idea (look at the previous exchanges):
  "Ti sei fissato sul pianoforte: smettila e chiedimi altro." / "Sembra che quel
  pianoforte ti piaccia molto. Posso fissarvi un appuntamento, ma per risolverlo non serve."
- irrelevant: be creative, even absurd, and invent a detail, but say in the same sentence
  that it does not matter for the story:
  "Mah, magari era nero. Ma per la storia non conta niente." / "Diciamo che aveva i
  calzini a pois: tanto per quello che è successo non cambia nulla."
- invalid: answer what the player actually did. A vague or open question: "Questa è una
  domanda vaga, non riesco a risponderti." Two options in one question ("è stata la
  moglie o il direttore?"): play along without choosing, e.g. "Mi fai scegliere? Troppo
  comodo: chiedimele una alla volta." Remind that you answer yes or no only if the player
  keeps asking open questions.
- unclear: "Eh? Non ho capito." / "Cosa hai detto? Non ti ho sentito." / "Non ti sento,
  c'è troppo casino."
- WITHIN REACH (this question found the last thing needed to solve), after the answer:
  "Ok, sembri a un ottimo punto: riesci a darmi un'ipotesi finale?" / "Ok, perfetto. Ora
  fammi un riepilogo di tutta la storia."

Write only the sentence the player hears."""

REPLY_CONFIG = types.GenerateContentConfig(
    system_instruction=CONDUCTOR_RULES,
    temperature=0.9,   # variety is the point: the check in code keeps it safe
    response_mime_type="application/json",
    response_schema={"type": "OBJECT", "properties": {"reply": {"type": "STRING"}}, "required": ["reply"]},
)


def text_words(text):
    """Return every word of a text, in both readings of apostrophes (see `judge.words`)."""
    plain, spaced = words(text)
    return plain | spaced


class Conductor:
    """Turns an answered question into the sentence the player hears.

    Attributes:
        riddle: The `Riddle` being played.
        client: A `genai.Client`, e.g. from `make_client`.
        model: The conductor's model.
        max_attempts: Calls per request before giving up on a retryable error.
    """

    def __init__(self, riddle, client, model=CONDUCTOR_MODEL, max_attempts=MAX_ATTEMPTS):
        """Keep the riddle and the settings of the calls.

        Args:
            riddle: The `Riddle` being played.
            client: A `genai.Client`, e.g. from `make_client`.
            model: The conductor's model.
            max_attempts: Calls per request: high for evaluation, low in a live game.
        """
        self.riddle = riddle
        self.client = client
        self.model = model
        self.max_attempts = max_attempts

    def reply(self, question, verdict, history, session, new_facts, state, said_before=()):
        """Write the sentence for one answered question.

        Args:
            question: The player's words.
            verdict: The verdict from `Judge.answer`.
            history: (positive question, answer) pairs before this question.
            session: The `Session` of the game, after `unlock`.
            new_facts: Ids of the facts this question found.
            state: The dict from `Session.record`.
            said_before: The conductor's earlier sentences in this game.

        Returns:
            A dict with "reply" (the sentence) and "revealed" (the words that sent
            back the plain answer, empty when the sentence passed the check).
        """
        found = [fact["text"] for fact_id, fact in self.riddle.facts.items() if fact_id in session.found]
        new = [self.riddle.facts[fact_id]["text"] for fact_id in new_facts]
        recent = history[-RECENT_SIZE:]
        lines = lambda items: "\n".join(f"- {item}" for item in items) or "- none"
        contents = (f"STORY: {self.riddle.story}\n\n"
                    f"FACTS FOUND SO FAR:\n{lines(found)}\n\n"
                    f"FOUND BY THIS QUESTION:\n{lines(new)}\n\n"
                    f"PREVIOUS EXCHANGES:\n{lines(f'{q} -> {a}' for q, a in recent)}\n\n"
                    f"PLAYER'S WORDS: {question}\n"
                    f"QUESTION AS UNDERSTOOD: {verdict['positive_question']}\n"
                    f"ANSWER: {verdict['answer']}\n"
                    f"YOUR LAST SENTENCES:\n{lines(list(said_before)[-OWN_SIZE:])}\n\n"
                    f"REPEATED QUESTION: {'yes' if state['repeated'] else 'no'}\n"
                    f"RELIEF: {'yes, after ' + str(state['empty_streak']) + ' questions without progress' if state['relief'] else 'no'}\n"
                    f"WITHIN REACH: {'yes' if state['within_reach'] else 'no'}")
        sentence = json.loads(call_model(self.client, self.model, contents, REPLY_CONFIG,
                                         self.max_attempts).text)["reply"]

        # the safety net: words of facts not found yet that nobody has said
        said = [question, verdict["positive_question"], self.riddle.story, *found, *(q for q, _ in recent)]
        allowed = set().union(*(text_words(text) for text in said)) | STOPWORDS
        hidden = set().union(*(text_words(fact["text"]) for fact_id, fact in self.riddle.facts.items()
                               if fact_id not in session.found))
        revealed = sorted((text_words(sentence) & hidden) - allowed)
        return {"reply": PLAIN[verdict["answer"]] if revealed else sentence, "revealed": revealed}