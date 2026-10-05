"""Evaluate the judge on a puzzle's labelled test questions.

Run from the repository root:
    python -m riddle.evaluate
    python -m riddle.evaluate --puzzle gabbiano --language it --model gemini-3.5-flash-lite
"""

import argparse
import time

from riddle.judge import JUDGE_MODEL, Judge, make_client
from riddle.puzzle import load_arbiter, load_puzzle, load_tests


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
    between runs.

    Args:
        judge: A `Judge` built on a puzzle from `load_arbiter`.
        tests: Test cases from `load_tests`.
        runs: How many times every question is asked.

    Returns:
        One row per test, with the expected answer and the answers and
        rewrites of every run.
    """
    rows = [{"group": case["group"], "question": case["question"], "expected_answer": case["answer"],
             "answers": [], "rewritten": []} for case in tests]
    for run in range(1, runs + 1):
        for i, (case, row) in enumerate(zip(tests, rows), 1):
            print(f"\r{judge.model}: run {run}/{runs}, {i}/{len(tests)}", end="", flush=True)
            verdict = judge.answer(case["question"], case["history"], case["lit"])
            row["answers"].append(verdict["answer"])
            row["rewritten"].append(verdict["positive_question"])
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



def main():
    """Parse the command line, run the evaluation and print the report."""
    parser = argparse.ArgumentParser(description="Evaluate the judge on a puzzle's test questions.")
    parser.add_argument("--puzzle", default="gabbiano")
    parser.add_argument("--language", default="it")
    parser.add_argument("--model", default=JUDGE_MODEL)
    parser.add_argument("--answers-only", action="store_true",
                        help="judge only the answers, on a puzzle with only the arbiter's fields")
    parser.add_argument("--runs", type=int, default=3, help="runs per question with --answers-only")
    args = parser.parse_args()

    # the arbiter alone: the puzzle has no cards, so there is nothing else to judge
    if args.answers_only:
        judge = Judge(load_arbiter(args.puzzle, args.language), make_client(), args.model)
        report_answers(evaluate_answers(judge, load_tests(args.puzzle, args.language), args.runs), args.runs)
        return

    puzzle = load_puzzle(args.puzzle, args.language)
    judge = Judge(puzzle, make_client(), args.model)
    report(evaluate(judge, load_tests(args.puzzle, args.language)))


if __name__ == "__main__":
    main()