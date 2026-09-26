"""Evaluate the judge on a puzzle's labelled test questions.

Run from the repository root:
    python -m riddle.evaluate
    python -m riddle.evaluate --puzzle gabbiano --language it --model gemini-3.5-flash-lite
"""

import argparse
import time

from riddle.judge import JUDGE_MODEL, Judge, make_client
from riddle.puzzle import load_puzzle, load_tests


def evaluate(judge, tests):
    """Judge every test question and compare the result with its label.

    Cards already lit in a test's context are left out of both sides, so only
    the cards unlocked by the question itself are compared. Cards are compared
    after adding the cards they imply, since that is what the player sees.

    Args:
        judge: The `Judge` to evaluate.
        tests: Test cases from `load_tests`.

    Returns:
        One row per test, with expected and obtained answer and cards, and latency.
    """
    rows = []
    for i, case in enumerate(tests, 1):
        print(f"\r{judge.model}: {i}/{len(tests)}", end="", flush=True)   # flush: show progress at once
        known = judge.puzzle.closure(case["lit"])
        start = time.time()
        verdict = judge.judge(case["question"], case["history"], case["lit"])
        rows.append({
            "group": case["group"], "question": case["question"], "rewritten": verdict["positive_question"],
            "expected_answer": case["answer"], "answer": verdict["answer"],
            "expected_cards": judge.puzzle.closure(case["cards"]) - known,
            "cards": judge.puzzle.closure(verdict["cards"]) - known,
            "seconds": time.time() - start,
        })
    print()
    return rows


def report(rows):
    """Print accuracy per group, cards given away, latency, then every mistake.

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
    seconds = sum(r["seconds"] for r in rows) / len(rows)
    print(f"{'TOTAL':<20}{answers:>9.0%}{cards:>9.0%}{extra:>7}   avg {seconds:.1f}s per question")

    print("\nMISTAKES")
    for r in rows:
        if r["answer"] != r["expected_answer"] or r["cards"] != r["expected_cards"]:
            print(f"- {r['question']}")
            print(f"    rewritten: {r['rewritten']}")
            print(f"    expected:  {r['expected_answer']:<11}{', '.join(sorted(r['expected_cards'])) or '-'}")
            print(f"    got:       {r['answer']:<11}{', '.join(sorted(r['cards'])) or '-'}")


def main():
    """Parse the command line, run the evaluation and print the report."""
    parser = argparse.ArgumentParser(description="Evaluate the judge on a puzzle's test questions.")
    parser.add_argument("--puzzle", default="gabbiano")
    parser.add_argument("--language", default="it")
    parser.add_argument("--model", default=JUDGE_MODEL)
    args = parser.parse_args()

    puzzle = load_puzzle(args.puzzle, args.language)
    judge = Judge(puzzle, make_client(), args.model)
    report(evaluate(judge, load_tests(args.puzzle, args.language)))


if __name__ == "__main__":
    main()