"""The conductor: the sentence the player hears after each answered question.

The arbiter decides what is true; the conductor only says it, like a person who
knows the story. It never sees the truth or the facts not found yet, so it cannot
reveal them: it gets the player's words, the answer, the facts already found and
the state of the game from the engine. It writes two parts: the answer, said back
with the player's own words, and a reaction about the game. Two checks in code keep
them honest: the answer may use only the player's words (adding a word is how a
sentence becomes false), and a reaction with a word of a hidden fact is dropped.
"""

import json
import random

from google.genai import types

from riddle.judge import JUDGE_MODEL, MAX_ATTEMPTS, call_model, words

CONDUCTOR_MODEL = JUDGE_MODEL
RECENT_SIZE = 6   # exchanges shown to the conductor, enough to notice a player stuck on one idea
OWN_SIZE = 6      # the conductor's own last sentences, so it does not open the same way twice
LONG_ANSWER = 6   # words beyond which an answer repeats the question: only counted, for the report
# the engine's reasons for a reaction after a yes or no: without one, the answer is said alone
REASONS = ("repeated", "within_reach")

# what the player hears when the conductor's sentence fails a check
PLAIN = {"yes": "Sì.", "no": "No.", "irrelevant": "Non conta per la storia.",
         "invalid": "Ti sembra una domanda da sì o no?", "unclear": "Eh? Non ho capito."}
# the only words an answer may add to the player's: the answer itself, and pronouns that
# point back to the question ("No, non lo sono."): they keep it vague and add nothing to the story
ANSWER_WORDS = {"si", "no", "non", "esatto", "giusto", "vero", "proprio", "cosi",
                "lo", "la", "li", "le", "l", "ne", "ci", "c", "e", "era", "erano", "cera", "cerano"}
NEGATIONS = {"no", "non"}
# an irrelevant joke must say that it does not matter, and must not hide a yes or no
DISCLAIMERS = {"conta", "cambia", "centra", "importa", "irrilevante", "rilevante", "sposta",
               "serve", "interessa", "influisce"}

# said when the player is stuck: no word of any story, so the engine picks them without a model;
# written by Federico (07/10), each said at most once per game
STUCK_LINES = [
    "Stai girando a vuoto.",
    "Mi sa che ti stai iniziando a perdere.",
    "Sono un po' di domande che non portano a niente, eh?",
    "Così non ne usciamo, eh.",
    "Mi sa che stai girando in tondo.",
    "Siamo un po' fermi, eh.",
    "Non stiamo andando da nessuna parte: cambia approccio.",
    "Prova a cambiare tipo di domanda.",
    "Ok, facciamo un respiro e ripartiamo.",
    "Ti stai perdendo. Prova un'altra strada.",
    "Mi sa che ci siamo incartati.",
    "Ok, così non stiamo scoprendo niente.",
    "Domande su domande, e ancora nulla.",
    "Mi sa che è ora di cambiare prospettiva.",
    "Ci stai mettendo impegno, ma per ora niente di nuovo.",
    "Tranquillo, succede a tutti di bloccarsi un po'.",
    "Non arrenderti, ma prova a ragionare diversamente.",
    "Fermati un attimo e ripensa a quello che sai già.",
    "Qui il tempo si è fermato, eh.",
    "Sto ancora aspettando una domanda che porti da qualche parte.",
    "Fai un passo indietro e riparti.",
    "Dai, scuoti un po' le idee.",
    "Sei bloccato, eh? Succede.",
    "Mi sa che serve un'idea nuova.",
    "Proviamo a pensarla in modo diverso?",
]
# said before a yes that finds a fact after many questions without one; a line with "sì" is the
# whole answer, a line ending with ":" is followed by it; written by Federico (07/10)
RELIEF_LINES = [
    "Finalmente una domanda utile!",
    "Era ora!",
    "Finalmente si sblocca qualcosa!",
    "Dopo ben {n} domande vaghe, abbiamo novità:",
    "Bravo, adesso sì che ragioniamo.",
    "Ah, ci voleva!",
    "Non ci speravo più!",
    "Alleluia!",
    "Signore e signori, abbiamo un sì!",
    "Ben fatto!",
    "Ottima ipotesi!",
    "Grazie a Dio!",
    "E il pubblico esulta: sì!",
    "È stata dura, ma eccolo qua: sì!",
    "Sì, sì e ancora sì!",
    "Grazie al cielo, sì!",
    "Fermate tutto: è un sì!",
    "Ottima domanda!",
]
# the answer speaks to the player: "devo capire...?" becomes "non devi capire..."
PERSON = {"devo": "devi", "posso": "puoi", "voglio": "vuoi", "sono": "sei", "ho": "hai",
          "io": "tu", "mi": "ti", "me": "te", "mio": "tuo", "mia": "tua", "miei": "tuoi", "mie": "tue"}

# common words that say nothing about a story: they never count as a revealed word
STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "del", "della", "dei", "delle",
    "a", "al", "alla", "ai", "da", "dal", "dalla", "in", "nel", "nella", "nei", "su", "sul", "sulla",
    "con", "per", "tra", "fra", "e", "ed", "o", "ma", "che", "non", "si", "ci", "ne", "se", "come",
    "suo", "sua", "suoi", "loro", "lui", "lei", "era", "erano", "ha", "hanno", "aveva", "avevano",
    "c", "l", "ce", "cera", "qualcosa", "cosa", "solo", "anche", "gia", "piu", "molto", "molti", "quel",
    "quello", "quella", "questo", "questa", "perche", "senza", "fare", "fa", "faceva", "fatto", "sono",
    "stato", "stata", "essere", "ancora", "sempre", "tutto", "tutti", "niente", "nulla", "mai", "poi",
    "quando", "dove", "qui", "cerano",
}

# the style card written by Federico (07/10); examples from an invented story (a pianist who
# stops playing mid-concert, his wife in the front row), never from a riddle under test
CONDUCTOR_RULES = """You are the voice of a lateral thinking game played by voice, in Italian.
You know there is a story; the player asks questions and another component has already
decided the answer. You only say it, as a real person would at the table.

WHAT YOU KNOW
You do NOT know the solution. You know only the visible story, the facts the player has
already found, the player's words and the answer.

WHAT YOU WRITE: three parts, joined in this order
- "answer": after yes or no, "Sì." or "No." alone, or a short answer that points back
  to the question instead of repeating it ("Sì, c'era." / "No, non lo sono." / "Sì,
  nevicava."). Stay as vague as the question: never add a word, a detail, a reason or a
  "nothing/everything". Repeat the question's words only to clear up a negation ("Non
  c'era cibo?" -> "Giusto, non c'era cibo."). A question about where to look is asked
  to you: answer it to the player ("Devo capire chi c'era in sala?" -> "No, non devi.").
  After irrelevant, invalid or unclear, write "".
- "before" and "after": a reaction about the GAME, never about the story. After yes or
  no, write one only when the game gives a reason below (REPEATED QUESTION, WITHIN
  REACH); otherwise both are "". After irrelevant, invalid or unclear, the
  reaction is the whole sentence.

HOW YOU SPEAK
1. Spoken Italian, short complete sentences.
2. Never say or suggest that something is important, close, right or wrong beyond the
   answer: no "ci siamo quasi", no "indizio utile", no hypotheses of your own.
3. No textbook sentences ("adesso le cose cambiano", "chiediti perché conta").
4. Irony is welcome when the question is irrelevant; never about the facts of the
   story, and never with images from the story's world (its places, weather, objects):
   they point the player somewhere.
5. Never open two sentences in a row the same way: your last sentences are listed.

WHAT THE GAME TELLS YOU, AND HOW IT SOUNDS
The examples show the tone, as before | answer | after. They are not sentences to copy:
vary them, invent your own in the same spirit.
- yes / no, no reason: "" | "Sì." | "" / "" | "No, non era malato." | ""
- REPEATED QUESTION:
  "Te lo ripeto:" | "sì." | "" / "La risposta non cambia, eh:" | "no." | ""
- WITHIN REACH (this question found the last thing needed to solve):
  "" | "Sì." | "Ok, sembri a un ottimo punto: riesci a darmi un'ipotesi finale?" /
  "" | "Sì." | "Ok, perfetto. Ora fammi un riepilogo di tutta la storia."
- irrelevant: a joke about the very thing asked, absurd and clearly invented, then say
  it does not matter; never a yes or no, never a conclusion about what happened:
  "Mah, magari era nero. Ma per la storia non conta niente." / "Diciamo che aveva i
  calzini a pois: tanto per quello che è successo non cambia nulla."
- invalid: answer what the player actually did. A vague or open question: "Questa è una
  domanda vaga, non riesco a risponderti." Two options in one question ("è stata la
  moglie o il direttore?"): "Mi fai scegliere? Troppo comodo: chiedimele una alla volta."
  Remind that you answer yes or no only if the player keeps asking open questions.
- unclear: "Eh? Non ho capito." / "Cosa hai detto? Non ti ho sentito." / "Non ti sento,
  c'è troppo casino."
"""

REPLY_CONFIG = types.GenerateContentConfig(
    system_instruction=CONDUCTOR_RULES,
    temperature=0.9,   # variety is the point: the checks in code keep it safe
    response_mime_type="application/json",
    response_schema={
        "type": "OBJECT",
        "properties": {"before": {"type": "STRING"}, "answer": {"type": "STRING"}, "after": {"type": "STRING"}},
        "required": ["before", "answer", "after"],
        "propertyOrdering": ["before", "answer", "after"],
    },
)


def text_words(text):
    """Return every word of a text, in both readings of apostrophes (see `judge.words`)."""
    plain, spaced = words(text)
    return plain | spaced


def answer_is_honest(sentence, question, verdict):
    """Check that an answer only says the arbiter's yes or no with the player's words.

    A word the player did not say is how a true answer becomes false ("la neve non ha
    coperto nulla"), so the answer may add only yes, no, "non" and the change of person
    of a question asked to the game. A yes may not carry a negation the question did not.

    Args:
        sentence: The answer part written by the conductor.
        question: The player's words.
        verdict: The verdict from `Judge.answer`.
    """
    asked = text_words(question) | text_words(verdict["positive_question"])
    allowed = asked | {PERSON.get(word, word) for word in asked} | ANSWER_WORDS
    said = text_words(sentence)
    if not said or not said <= allowed:
        return False
    if verdict["answer"] == "no":
        # "No, in bocca." sounds like the opposite: words after the no need a "non"
        return said == {"no"} or "non" in said
    return not (said & NEGATIONS) - text_words(verdict["positive_question"])


def joke_is_safe(sentence):
    """Check that an irrelevant joke says it does not matter and hides no yes or no.

    "Probabilmente sì, se..." answers a question the arbiter judged irrelevant.

    Args:
        sentence: The reaction written after an irrelevant question.
    """
    said = text_words(sentence)
    return bool(said & DISCLAIMERS) and not said & {"si", "no"}


def pick_line(bank, said_before):
    """Pick a line of a bank not said yet in this game (any of them once all are used).

    Args:
        bank: The lines to pick from, e.g. `STUCK_LINES` or `RELIEF_LINES`.
        said_before: The conductor's earlier sentences in this game.
    """
    # a line with a number is recognised by the words before it
    unused = [line for line in bank if not any(line.split("{")[0] in sentence for sentence in said_before)]
    return random.choice(unused or bank)


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
            A dict with "reply" (the sentence), "plain_answer" (the answer or the
            irrelevant joke failed its check and was cut to the plain line), "long_answer" (the answer repeats the
            question, to count in the report) and "revealed" (words of hidden facts
            that made the reaction drop, empty when it passed).
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
                    f"WITHIN REACH: {'yes' if state['within_reach'] else 'no'}")
        parts = json.loads(call_model(self.client, self.model, contents, REPLY_CONFIG, self.max_attempts).text)
        if verdict["answer"] not in ("yes", "no"):
            # without a yes or no the whole sentence is the reaction, whatever field the model put it in
            whole = " ".join(part for part in (parts["before"], parts["answer"], parts["after"]) if part.strip())
            parts = {"before": whole, "answer": "", "after": ""}

        # the answer: a yes or no said with the player's words, or just the plain yes or no
        answer, plain_answer = "", False
        if verdict["answer"] in ("yes", "no"):
            plain_answer = not answer_is_honest(parts["answer"], question, verdict)
            answer = PLAIN[verdict["answer"]] if plain_answer else parts["answer"]

        # the reaction: dropped if it names a hidden fact nobody has said
        reaction = f"{parts['before']} {parts['after']}"
        said = [question, verdict["positive_question"], self.riddle.story, *found, *(q for q, _ in recent)]
        allowed = set().union(*(text_words(text) for text in said)) | STOPWORDS
        hidden = set().union(*(text_words(fact["text"]) for fact_id, fact in self.riddle.facts.items()
                               if fact_id not in session.found))
        revealed = sorted((text_words(reaction) & hidden) - allowed)
        # after a yes or no a reaction needs a reason from the engine: the model does not choose when to react
        reason = verdict["answer"] not in ("yes", "no") or any(state[name] for name in REASONS)
        before, after = (parts["before"], parts["after"]) if reason and not revealed else ("", "")
        if verdict["answer"] == "irrelevant" and not joke_is_safe(f"{before} {after}"):
            before, after, plain_answer = "", "", True

        # relief: the opening comes from the bank, the model never writes it
        if state["relief"]:
            before = pick_line(RELIEF_LINES, said_before).format(n=state["empty_streak"])
            if "si" in text_words(before):
                answer = ""   # the line already says yes
        # an answer after a colon goes on with the same sentence: "Te lo ripeto: sì."
        if before.strip().endswith(":") and answer:
            answer = answer[0].lower() + answer[1:]

        sentence = " ".join(part for part in (before, answer, after) if part.strip())
        # nothing left to say after irrelevant, invalid or unclear: the plain line
        sentence = sentence or PLAIN[verdict["answer"]]
        # the engine says the player is stuck, with a line from the bank: after the answer, never instead of it
        if state["stuck"]:
            sentence = f"{sentence} {pick_line(STUCK_LINES, said_before)}"
        # "sì." follows a dropped "Te lo ripeto:": the sentence still starts with a capital
        return {"reply": sentence[0].upper() + sentence[1:], "plain_answer": plain_answer,
                "long_answer": len(answer.split()) > LONG_ANSWER, "revealed": revealed}