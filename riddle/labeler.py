"""Reference labeller: writes the answer an excellent host would give, to label test questions.

It is not part of the game. A stronger model than the arbiter, with its own
instructions (not the arbiter's rules, or it would repeat the arbiter's
mistakes), labels questions offline. It is checked once against hand labels;
then it labels simulated games, and only its disagreements with the arbiter
are reviewed by hand.

Run from the repository root:
    python -m riddle.labeler validate --puzzle baita   # against the hand labels
    python -m riddle.labeler label --puzzle baita      # simulated games -> logs/review.baita.json
    python -m riddle.labeler build --puzzle baita      # reviewed labels -> tests.simulated.it.json
"""

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path
import httpx

from concurrent.futures import ThreadPoolExecutor, as_completed

from google.genai import errors, types

from riddle.judge import make_client
from riddle.puzzle import ANSWERS, PUZZLES_DIR, load_arbiter, load_tests

LABELER_MODEL = "gemini-3.5-flash-lite"   # Flash on Vertex answered in 2 s or never: Lite is stable; checked by validate
MAX_ATTEMPTS = 6
LABEL_TIMEOUT_MS = 10_000   # a call with long reasoning takes up to a minute: past two, it hung

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
            thinking_config=types.ThinkingConfig(thinking_level="high"),   # the hard cases need reasoning
            http_options=types.HttpOptions(timeout=LABEL_TIMEOUT_MS))      # a hung call fails and is retried

    def label(self, question, earlier_questions):
        """Label one question.

        Args:
            question: The player's words.
            earlier_questions: The player's earlier questions in the same game, oldest first.

        Returns:
            A dict with "answer", "confident" and "reason", or None if the service kept failing.
        """
        earlier = "\n".join(f"- {q}" for q in earlier_questions) or "- none"
        contents = f"EARLIER QUESTIONS:\n{earlier}\n\nNEW QUESTION: {question}"
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self.client.models.generate_content(model=self.model, contents=contents, config=self.config)
                return json.loads(response.text)
            except (errors.APIError, httpx.TimeoutException) as e:
                reason = getattr(e, "code", "timeout")   # timeouts carry no HTTP code
                if reason not in (429, 503, 504, "timeout"):
                    raise   # a real error, e.g. a bad request: stop and show it
                if attempt == MAX_ATTEMPTS - 1:
                    # the service kept failing: skip this question rather than lose the whole run
                    print(f"\n[failed] {question}")
                    return None
                print(f"[retry] {self.model} got {reason}, waiting {2 ** attempt} s")
                time.sleep(2 ** attempt)


def validate(labeler, tests):
    """Label every test question and compare the labels with the hand labels.

    The earlier questions come from the test's history, without the answers
    given in the game, so a wrong answer in the game cannot lead the labeller.

    Args:
        labeler: The `Labeler` to check.
        tests: Test cases from `load_tests`; groups ending in "_doubtful" hold doubtful hand labels.
    """
    # in parallel, as in label_log: one slow call no longer holds up all the others
    labels = [None] * len(tests)
    with ThreadPoolExecutor(max_workers=LABEL_WORKERS) as pool:
        futures = {pool.submit(labeler.label, case["question"], [q for q, _ in case["history"]]): i
                   for i, case in enumerate(tests)}
        for done, future in enumerate(as_completed(futures), 1):
            labels[futures[future]] = future.result()
            print(f"\r{labeler.model}: {done}/{len(tests)}", end="", flush=True)
    print()
    # a label is None when the service kept failing: leave that question out
    rows = [{**label, "question": case["question"], "expected": case["answer"],
             "doubtful": case["group"].endswith("_doubtful")} for case, label in zip(tests, labels) if label]
    failed = len(tests) - len(rows)
    if failed:
        print(f"failed: {failed} (left out)")

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


REVIEW_SHARE = 0.1   # share of agreements checked by hand: both may be wrong in the same way
LABEL_WORKERS = 8   # parallel labelling calls: enough for speed, few enough for the rate limit


def label_log(labeler, puzzle_name):
    """Label every simulated question and write the ones a person must review.

    Each question is labelled with the player's own earlier words in the same
    game, unclear questions included. The labels are compared with the answer
    the arbiter gave during the game.

    Args:
        labeler: The `Labeler` of the puzzle.
        puzzle_name: Folder name of the puzzle, e.g. "baita".
    """
    review_file = Path(f"logs/review.{puzzle_name}.json")
    # never overwrite a review already started by hand
    if review_file.exists():
        raise SystemExit(f"{review_file} already exists: delete it to label again")

    rows = [json.loads(line) for line in open(f"logs/simulated.{puzzle_name}.jsonl", encoding="utf-8")]
    # the player's earlier words come from the log, so every label can be asked at once
    earlier = {}   # game -> the player's questions so far
    for row in rows:
        before = earlier.setdefault(row["game"], [])
        row["earlier"] = list(before)
        before.append(row["question"])
    # each call takes several seconds of reasoning: in parallel they take minutes, not most of an hour
    labels = [None] * len(rows)
    with ThreadPoolExecutor(max_workers=LABEL_WORKERS) as pool:
        futures = {pool.submit(labeler.label, r["question"], r["earlier"]): i for i, r in enumerate(rows)}
        # labels arrive in any order: count them as they come, and put each one back in its place
        for done, future in enumerate(as_completed(futures), 1):
            labels[futures[future]] = future.result()
            print(f"\r{labeler.model}: {done}/{len(rows)}", end="", flush=True)
    print()
    for row, label in zip(rows, labels):
        row["label"] = label
    # all the labels, so that build needs no model calls
    Path(f"logs/labeled.{puzzle_name}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    agree = [r for r in rows if r["label"]["answer"] == r["answer"]]
    print(f"agreement: {len(agree)}/{len(rows)}")
    for persona in dict.fromkeys(r["persona"] for r in rows):
        sub = [r for r in rows if r["persona"] == persona]
        print(f"  {persona:<11} {sum(r in agree for r in sub)}/{len(sub)}")
    # the kinds of disagreement show the kinds of mistake at a glance
    print("\ndisagreements (arbiter -> labeller):")
    for (got, label), n in Counter((r["answer"], r["label"]["answer"]) for r in rows
                                   if r not in agree).most_common():
        print(f"  {got} -> {label}: {n}")

    # to review: every disagreement, every doubtful label, and a fixed random share of the agreements
    to_check = [(r, "disagreement") for r in rows if r not in agree]
    to_check += [(r, "not confident") for r in agree if not r["label"]["confident"]]
    sure = [r for r in agree if r["label"]["confident"]]
    to_check += [(r, "random check") for r in random.Random(0).sample(sure, round(len(sure) * REVIEW_SHARE))]
    review = [{"timestamp": r["timestamp"], "why": why, "persona": r["persona"], "earlier": r["earlier"],
               "question": r["question"], "arbiter": r["answer"], "labeller": r["label"]["answer"],
               "confident": r["label"]["confident"], "reason": r["label"]["reason"], "final": ""}
              for r, why in to_check]
    review_file.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nto review: {len(review)} -> {review_file} (write the right answer in \"final\")")


def build_simulated(puzzle_name, language):
    """Write the simulated questions as test cases, with the reviewed labels where given.

    Args:
        puzzle_name: Folder name of the puzzle.
        language: Language code of the test file.
    """
    rows = json.loads(Path(f"logs/labeled.{puzzle_name}.json").read_text(encoding="utf-8"))
    review = json.loads(Path(f"logs/review.{puzzle_name}.json").read_text(encoding="utf-8"))
    final = {item["timestamp"]: item["final"] for item in review if item["final"]}
    unknown = set(final.values()) - set(ANSWERS)
    if unknown:
        raise SystemExit(f"unknown answers in the review: {sorted(unknown)}")

    # the reviewed answer wins; otherwise the labeller's
    tests = [{"group": r["persona"], "question": r["question"],
              "answer": final.get(r["timestamp"], r["label"]["answer"]),
              "cards": [], "lit": [], "history": r["history"]} for r in rows]
    path = PUZZLES_DIR / puzzle_name / f"tests.simulated.{language}.json"
    path.write_text(json.dumps(tests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"test cases: {len(tests)} ({len(final)} reviewed by hand) -> {path}")


def main():
    """Parse the command line and run one step: validate, label or build."""
    parser = argparse.ArgumentParser(description="Reference labeller for test questions.")
    parser.add_argument("step", choices=["validate", "label", "build"],
                        help="validate on hand labels, label the simulated games, or build their test cases")
    parser.add_argument("--puzzle", default="baita")
    parser.add_argument("--language", default="it")
    parser.add_argument("--model", default=LABELER_MODEL)
    args = parser.parse_args()

    # build only reads files: no model needed
    if args.step == "build":
        build_simulated(args.puzzle, args.language)
        return
    labeler = Labeler(load_arbiter(args.puzzle, args.language), make_client(), args.model)
    if args.step == "validate":
        validate(labeler, load_tests(args.puzzle, args.language))
    else:
        label_log(labeler, args.puzzle)


if __name__ == "__main__":
    main()