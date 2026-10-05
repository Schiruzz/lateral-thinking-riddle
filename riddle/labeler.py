"""Reference labeller: writes the answer an excellent host would give, to label test questions.

It is not part of the game. A stronger model than the arbiter, with its own
instructions (not the arbiter's rules, or it would repeat the arbiter's
mistakes), labels questions offline. It is checked once against hand labels;
then it labels simulated games, and only its disagreements with the arbiter
are reviewed by hand.

Run from the repository root:
    python -m riddle.labeler validate --puzzle baita
"""

import argparse
import json
import time

from google.genai import errors, types

from riddle.judge import make_client
from riddle.puzzle import ANSWERS, load_arbiter, load_tests

LABELER_MODEL = "gemini-3.5-flash"   # stronger than the arbiter: offline, so slow calls are fine
MAX_ATTEMPTS = 6

LABELER_PROMPT = """You label test questions for a lateral thinking puzzle played by voice. A player who
does not know the hidden truth asks questions about a mysterious situation; a host who
knows the truth answers. For each question, write the answer an excellent human host
would give. You write the reference answer: you are not playing.

You get the visible situation (all the player knows), the hidden truth as a story and
as a list of facts, the player's earlier questions in this game (without the answers
they received), and the new question.

THE SIX ANSWERS
- yes: read as a yes/no question about the story, it is true.
- no: it is false. This includes questions built on a false assumption: "Devo capire
  chi l'ha spinto?" when nobody pushed him is no.
- irrelevant: the question is clear, but nothing in the hidden truth decides it and it
  does not matter for understanding what happened ("Era un uomo ricco?"). A detail the
  truth does not mention is irrelevant, not no.
- partly: true, but it points at a part of the story that does not hold the key, so
  the player should look elsewhere. Rare.
- invalid: not a yes/no question about the story: an open question ("Come è morto?"),
  a request for the solution or for hints ("Sono sulla strada giusta?"), or a question
  about the game. A statement of what happened is a hypothesis to judge, never invalid,
  however long or badly worded.
- unclear: even after reading obvious slips correctly, the words make no sense, so you
  cannot tell what was asked.

HOW TO READ A QUESTION
1. Players speak or type fast: read typos, missing accents, digits and voice
   transcription slips as what was clearly meant ("E caduto" = "È caduto",
   "telegiornalle" = "telegiornale", "3 amici" = "tre amici").
2. Statements and guesses are questions ("secondo me si è buttato" = "Si è buttato?").
3. Negations: label the positive form. "Non era solo in casa?" is labelled as
   "Era solo in casa?".
4. Short questions continue the earlier ones: "Dalle scale?" after "È caduto?" means
   "È caduto dalle scale?".
5. Read words with their everyday meaning, as an ordinary Italian speaker would.
6. Several claims in one question: yes only if every claim is true; no if any claim is
   false; if the truth decides some claims and not others, label by the ones it
   decides and set confident to false.
7. "Where to look" questions ("Devo concentrarmi sul mare?", "Il telegiornale è
   importante?"): yes if that part matters for the solution, irrelevant if it does
   not, no if the question assumes something false.
8. Judgements ("È stato sfortunato?", "È una cosa che può succedere?"): answer them if
   the truth decides them, even loosely; otherwise irrelevant.

CONFIDENCE
Set confident to false when a careful host could reasonably give a different answer:
ambiguous words, or a judgement the truth barely supports. Name the other answer in
the reason.

OUTPUT
- answer: one of yes, no, irrelevant, partly, invalid, unclear
- confident: true or false
- reason: one short sentence naming the fact that decides the answer"""

LABEL_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "answer": {"type": "STRING", "enum": list(ANSWERS)},
        "confident": {"type": "BOOLEAN"},
        "reason": {"type": "STRING"},
    },
    "required": ["answer", "confident", "reason"],
    "propertyOrdering": ["reason", "answer", "confident"],   # the reason first: the answer follows from it
}


class Labeler:
    """Labels questions of one puzzle with the answer an excellent host would give.

    Attributes:
        client: The Vertex AI client.
        model: The labelling model.
        config: The labeller's config, with the puzzle's whole truth in the instructions.
    """

    def __init__(self, puzzle, client, model=LABELER_MODEL):
        """Put the puzzle's story and whole truth in the instructions, once.

        Args:
            puzzle: A puzzle from `load_arbiter`: it needs story, solution and solution facts.
            client: A `genai.Client`, e.g. from `make_client`.
            model: The labelling model.
        """
        self.client = client
        self.model = model
        facts = "\n".join(f"- {fact}" for fact in puzzle.solution_facts)
        prompt = (f"{LABELER_PROMPT}\n\nVISIBLE SITUATION: {puzzle.story}\n\n"
                  f"HIDDEN TRUTH (story): {puzzle.solution}\n\nHIDDEN TRUTH (facts):\n{facts}")
        self.config = types.GenerateContentConfig(
            system_instruction=prompt, temperature=0,
            response_mime_type="application/json", response_schema=LABEL_SCHEMA,
            thinking_config=types.ThinkingConfig(thinking_level="high"))   # the hard cases need reasoning

    def label(self, question, earlier_questions):
        """Label one question.

        Args:
            question: The player's words.
            earlier_questions: The player's earlier questions in the same game, oldest first.

        Returns:
            A dict with "answer", "confident" and "reason".
        """
        earlier = "\n".join(f"- {q}" for q in earlier_questions) or "- none"
        contents = f"EARLIER QUESTIONS:\n{earlier}\n\nNEW QUESTION: {question}"
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self.client.models.generate_content(model=self.model, contents=contents, config=self.config)
                return json.loads(response.text)
            except errors.APIError as e:
                # rate limits and overloads pass: wait longer each time, then give up
                if e.code not in (429, 503, 504) or attempt == MAX_ATTEMPTS - 1:
                    raise
                time.sleep(2 ** attempt)


def validate(labeler, tests):
    """Label every test question and compare the labels with the hand labels.

    The earlier questions come from the test's history, without the answers
    given in the game, so a wrong answer in the game cannot lead the labeller.

    Args:
        labeler: The `Labeler` to check.
        tests: Test cases from `load_tests`; groups ending in "_doubtful" hold doubtful hand labels.
    """
    rows = []
    for i, case in enumerate(tests, 1):
        print(f"\r{labeler.model}: {i}/{len(tests)}", end="", flush=True)
        label = labeler.label(case["question"], [q for q, _ in case["history"]])
        rows.append({**label, "question": case["question"], "expected": case["answer"],
                     "doubtful": case["group"].endswith("_doubtful")})
    print()

    def agreement(sub):
        return f"{sum(r['answer'] == r['expected'] for r in sub)}/{len(sub)}" if sub else "-"

    clear = [r for r in rows if not r["doubtful"]]
    doubtful = [r for r in rows if r["doubtful"]]
    print(f"agreement, clear labels:    {agreement(clear)}")
    print(f"agreement, doubtful labels: {agreement(doubtful)}")
    print(f"agreement, all:             {agreement(rows)}")
    # do labeller and hand labels find the same questions hard?
    not_confident = [r for r in rows if not r["confident"]]
    print(f"labeller not confident:     {len(not_confident)} ({sum(r['doubtful'] for r in not_confident)} of them doubtful by hand)")

    print("\nDISAGREEMENTS")
    for r in rows:
        if r["answer"] != r["expected"]:
            tag = "doubtful" if r["doubtful"] else "clear"
            print(f"- [{tag}] {r['question']}")
            print(f"    hand:     {r['expected']}")
            print(f"    labeller: {r['answer']}{'' if r['confident'] else ' (not confident)'}: {r['reason']}")


def main():
    """Parse the command line and validate the labeller on a puzzle's hand labels."""
    parser = argparse.ArgumentParser(description="Check the reference labeller against hand labels.")
    parser.add_argument("step", choices=["validate"])
    parser.add_argument("--puzzle", default="baita")
    parser.add_argument("--language", default="it")
    parser.add_argument("--model", default=LABELER_MODEL)
    args = parser.parse_args()

    puzzle = load_arbiter(args.puzzle, args.language)
    labeler = Labeler(puzzle, make_client(), args.model)
    validate(labeler, load_tests(args.puzzle, args.language))


if __name__ == "__main__":
    main()