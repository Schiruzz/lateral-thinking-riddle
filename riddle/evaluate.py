"""Evaluate the judge on a puzzle's labelled test questions.

Run from the repository root:
    python -m riddle.evaluate
    python -m riddle.evaluate --puzzle gabbiano --language it --model gemini-3.5-flash-lite
"""

import argparse
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from riddle.engine import Session
from riddle.judge import JUDGE_MODEL, Judge, Matcher, make_client
from riddle.puzzle import PUZZLES_DIR, load_arbiter, load_puzzle, load_tests
from riddle.schema import load_riddle

EVAL_WORKERS = 8   # questions judged at once: minutes instead of most of an hour, within the rate limit

EVAL_WORKERS = 8   # questions judged at once: minutes instead of most of an hour, within the rate limit


def evaluate(judge, tests):
    """Judge every test question and compare the result with its label.

    Each question goes through the game's two steps: the answer, then the
    cards. Cards already lit in a test's context are left out of both sides,
    so only the cards unlocked by the question itself are compared. Cards are
    compared after adding the cards they imply, since that is what the player sees.

    Args:
        judge: The `Judge` to evaluate.
        tests: Test cases from `load_tests`.

    Returns:
        One row per test, with expected and obtained answer and cards, and the
        time of each step.
    """
    rows = []
    for i, case in enumerate(tests, 1):
        print(f"\r{judge.model}: {i}/{len(tests)}", end="", flush=True)   # flush: show progress at once
        known = judge.puzzle.closure(case["lit"])
        start = time.time()
        verdict = judge.answer(case["question"], case["history"], case["lit"])
        answered = time.time()
        cards = judge.cards(case["question"], verdict, case["history"], case["lit"])
        rows.append({
            "group": case["group"], "question": case["question"], "rewritten": verdict["positive_question"],
            "expected_answer": case["answer"], "answer": verdict["answer"],
            "expected_cards": judge.puzzle.closure(case["cards"]) - known,
            "cards": judge.puzzle.closure(cards) - known,
            "answer_seconds": answered - start, "cards_seconds": time.time() - answered,
        })
    print()
    return rows


def report(rows):
    """Print accuracy per group, cards given away, time per step, then every mistake.

    Args:
        rows: The rows returned by `evaluate`.
    """
    print(f"{'group':<20}{'answers':>9}{'cards':>9}{'extra':>7}")
    for group in dict.fromkeys(r["group"] for r in rows):
        sub = [r for r in rows if r["group"] == group]
        answers = sum(r["answer"] == r["expected_answer"] for r in sub) / len(sub)
        cards = sum(r["cards"] == r["expected_cards"] for r in sub) / len(sub)
        extra = sum(len(r["cards"] - r["expected_cards"]) for r in sub)
        print(f"{group:<20}{answers:>9.0%}{cards:>9.0%}{extra:>7}")

    answers = sum(r["answer"] == r["expected_answer"] for r in rows) / len(rows)
    cards = sum(r["cards"] == r["expected_cards"] for r in rows) / len(rows)
    extra = sum(len(r["cards"] - r["expected_cards"]) for r in rows)
    print(f"{'TOTAL':<20}{answers:>9.0%}{cards:>9.0%}{extra:>7}")

    # average and worst case of each step: a high maximum means retries on rate limits or timeouts
    print(f"\n{'step':<10}{'avg s':>8}{'max s':>8}")
    for step in ("answer", "cards"):
        seconds = [r[f"{step}_seconds"] for r in rows]
        print(f"{step:<10}{sum(seconds) / len(seconds):>8.1f}{max(seconds):>8.1f}")

    print("\nMISTAKES")
    for r in rows:
        if r["answer"] != r["expected_answer"] or r["cards"] != r["expected_cards"]:
            print(f"- {r['question']}")
            print(f"    rewritten: {r['rewritten']}")
            print(f"    expected:  {r['expected_answer']:<11}{', '.join(sorted(r['expected_cards'])) or '-'}")
            print(f"    got:       {r['answer']:<11}{', '.join(sorted(r['cards'])) or '-'}")



def evaluate_answers(judge, tests, runs):
    """Ask the arbiter every test question several times, without cards.

    Repeating the runs separates stable mistakes from the normal swing
    between runs. Every question of every run is independent, so they are
    all asked in parallel.

    Args:
        judge: A `Judge` built on a puzzle from `load_arbiter` or `load_puzzle`.
        tests: Test cases from `load_tests`.
        runs: How many times every question is asked.

    Returns:
        One row per test, with the expected answer and the answers and
        rewrites of every run.
    """
    rows = [{"group": case["group"], "question": case["question"], "expected_answer": case["answer"],
             "answers": [], "rewritten": []} for case in tests]
    jobs = [(i, case) for _ in range(runs) for i, case in enumerate(tests)]
    with ThreadPoolExecutor(max_workers=EVAL_WORKERS) as pool:
        futures = {pool.submit(judge.answer, case["question"], case["history"], case["lit"]): i
                   for i, case in jobs}
        # answers arrive in any order: each goes to its question's row, and runs are only counted
        for done, future in enumerate(as_completed(futures), 1):
            verdict = future.result()
            row = rows[futures[future]]
            row["answers"].append(verdict["answer"])
            row["rewritten"].append(verdict["positive_question"])
            print(f"\r{judge.model}: {done}/{len(jobs)}", end="", flush=True)
    print()
    return rows


def report_answers(rows, runs):
    """Print answer accuracy per group, then every question missed in at least one run.

    Args:
        rows: The rows returned by `evaluate_answers`.
        runs: How many runs each row holds.
    """
    def accuracy(sub):
        # every run of every question counts once
        return sum(a == r["expected_answer"] for r in sub for a in r["answers"]) / (len(sub) * runs)

    print(f"{'group':<28}{'questions':>10}{'answers':>9}")
    for group in dict.fromkeys(r["group"] for r in rows):
        sub = [r for r in rows if r["group"] == group]
        print(f"{group:<28}{len(sub):>10}{accuracy(sub):>9.0%}")
    print(f"{'TOTAL':<28}{len(rows):>10}{accuracy(rows):>9.0%}")

    # most stable mistakes first: wrong in every run means it is not the swing between runs
    print(f"\nMISTAKES (wrong runs / {runs})")
    for r in sorted(rows, key=lambda r: -sum(a != r["expected_answer"] for a in r["answers"])):
        wrong = sum(a != r["expected_answer"] for a in r["answers"])
        if wrong:
            print(f"- {wrong}/{runs}  [{r['group']}]  {r['question']}")
            print(f"    rewritten: {' | '.join(dict.fromkeys(r['rewritten']))}")   # each different rewrite once
            print(f"    expected:  {r['expected_answer']}")
            print(f"    got:       {', '.join(r['answers'])}")



def play(riddle, ids):
    """Start a game and apply facts and false leads to it, as the engine would.

    Args:
        riddle: The `Riddle` being played.
        ids: Ids of facts and false leads, mixed.

    Returns:
        The `Session` after unlocking the facts and closing the leads.
    """
    session = Session(riddle)
    session.unlock([item_id for item_id in ids if item_id in riddle.facts])
    session.exclude([item_id for item_id in ids if item_id in riddle.exclusions])
    return session


def evaluate_facts(matcher, tests):
    """Match every test question and compare what it adds to the game with its label.

    The matcher gets the labelled answer, not the arbiter's: it is measured on its
    own, and the arbiter's mistakes stay in `--answers-only`. Both sides are compared
    after the engine has applied them, so presupposed facts and leads closed by a
    fact count as the player sees them.

    Args:
        matcher: The `Matcher` to evaluate.
        tests: Test cases from `load_tests`.

    Returns:
        One row per test, with the expected and obtained additions and the seconds taken.
    """
    riddle = matcher.riddle

    def run(case):
        before = play(riddle, case["lit"])
        known = before.found | before.excluded
        verdict = {"positive_question": case["question"], "answer": case["answer"]}
        start = time.time()
        facts, leads = matcher.match(case["question"], verdict, case["history"], before)
        seconds = time.time() - start
        expected = play(riddle, case["lit"] + case["cards"])
        got = play(riddle, case["lit"] + facts + leads)
        return {"group": case["group"], "question": case["question"], "answer": case["answer"],
                "expected": (expected.found | expected.excluded) - known,
                "got": (got.found | got.excluded) - known, "seconds": seconds}

    rows = [None] * len(tests)
    with ThreadPoolExecutor(max_workers=EVAL_WORKERS) as pool:
        futures = {pool.submit(run, case): i for i, case in enumerate(tests)}
        for done, future in enumerate(as_completed(futures), 1):
            rows[futures[future]] = future.result()
            print(f"\r{matcher.model}: {done}/{len(tests)}", end="", flush=True)
    print()
    return rows


def report_facts(rows, key_facts):
    """Print exact matches, facts given away and facts missed per group, the time, then every mistake.

    Args:
        rows: The rows returned by `evaluate_facts`.
        key_facts: Ids of the riddle's key facts, counted again in their own columns.
    """
    def line(name, sub):
        exact = sum(r["got"] == r["expected"] for r in sub) / len(sub)
        extra = sum(len(r["got"] - r["expected"]) for r in sub)      # given away: the worst mistake
        missing = sum(len(r["expected"] - r["got"]) for r in sub)
        # a key fact given away spoils the discovery; a key fact missed leaves the player unrewarded
        key_extra = sum(len((r["got"] - r["expected"]) & key_facts) for r in sub)
        key_missing = sum(len((r["expected"] - r["got"]) & key_facts) for r in sub)
        print(f"{name:<28}{len(sub):>10}{exact:>8.0%}{extra:>7}{missing:>9}{key_extra:>11}{key_missing:>13}")

    print(f"{'group':<28}{'questions':>10}{'exact':>8}{'extra':>7}{'missing':>9}{'key extra':>11}{'key missing':>13}")
    for group in dict.fromkeys(r["group"] for r in rows):
        line(group, [r for r in rows if r["group"] == group])
    line("TOTAL", rows)

    # a high maximum means retries on rate limits or timeouts
    seconds = [r["seconds"] for r in rows]
    print(f"\nseconds per question: avg {sum(seconds) / len(seconds):.1f}, max {max(seconds):.1f}")

    print("\nMISTAKES")
    for r in rows:
        if r["got"] != r["expected"]:
            print(f"- [{r['group']}]  {r['question']}  -> {r['answer']}")
            print(f"    expected:  {', '.join(sorted(r['expected'])) or '-'}")
            print(f"    got:       {', '.join(sorted(r['got'])) or '-'}")



def main():
    """Parse the command line, run the evaluation and print the report."""
    parser = argparse.ArgumentParser(description="Evaluate the judge on a puzzle's test questions.")
    parser.add_argument("--puzzle", default="gabbiano")
    parser.add_argument("--language", default="it")
    parser.add_argument("--model", default=JUDGE_MODEL)
    parser.add_argument("--answers-only", action="store_true",
                        help="judge only the answers, on a puzzle with only the arbiter's fields")
    parser.add_argument("--runs", type=int, default=3, help="runs per question with --answers-only")
    parser.add_argument("--tests", default=None, help="test set, e.g. simulated (default: the main one)")
    parser.add_argument("--grep", default=None,
                        help="with --answers-only, judge only the questions matching this pattern, e.g. \"cause naturali|infarto\"")
    parser.add_argument("--facts", action="store_true",
                        help="judge only the matcher, on a riddle in the card schema, with the labelled answers")
    parser.add_argument("--no-verifier", action="store_true", help="with --facts, the matcher without the verifier")
    args = parser.parse_args()

    # the matcher alone: what each question adds to the game
    if args.facts:
        matcher = Matcher(load_riddle(args.puzzle, args.language), make_client(), args.model,
                          use_verifier=not args.no_verifier)
        report_facts(evaluate_facts(matcher, load_tests(args.puzzle, args.language, args.tests)),
                     matcher.riddle.key_facts)
        return


    # the arbiter alone: the puzzle has no cards, so there is nothing else to judge
    if args.answers_only:
        # a full puzzle works too: its cards give the arbiter the context of the cards lit in a test
        arbiter_only = (PUZZLES_DIR / args.puzzle / f"arbiter.{args.language}.json").exists()
        puzzle = (load_arbiter if arbiter_only else load_puzzle)(args.puzzle, args.language)
        judge = Judge(puzzle, make_client(), args.model)
        tests = load_tests(args.puzzle, args.language, args.tests)
        # a quick check after a change: only the questions it touches
        if args.grep:
            tests = [case for case in tests if re.search(args.grep, case["question"], re.IGNORECASE)]
            print(f"questions matching {args.grep!r}: {len(tests)}")
        report_answers(evaluate_answers(judge, tests, args.runs), args.runs)
        return

    puzzle = load_puzzle(args.puzzle, args.language)
    judge = Judge(puzzle, make_client(), args.model)
    report(evaluate(judge, load_tests(args.puzzle, args.language, args.tests)))


if __name__ == "__main__":
    main()