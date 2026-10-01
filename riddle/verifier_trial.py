"""Trial: which model and thinking level make a fast and accurate verifier?

Runs the same checks with each setup: cards the test questions do state
(should be accepted) and cards they only hint at (should be refused).
Prints time and accuracy per setup, and the decisions that change from the
first setup. The game does not use this file.

Run from the repository root:
    python -m riddle.verifier_trial
"""

import json
import time

from google.genai import types

from riddle.judge import NEGATION, VERIFY_CONFIG, Judge, make_client
from riddle.puzzle import load_puzzle, load_tests

# (model, thinking level): Flash with "low", the game's setting, times out these days
SETUPS = [("gemini-3.5-flash-lite", "low"), ("gemini-3.5-flash", "minimal")]
POSITIVE_CHECKS = 25          # how many stated cards to check, enough to see a trend

# questions that only hint at a card: the verifier must refuse it
HINTS = [
    ("C'entra il mare?", "yes", "naufragio"),
    ("Avevano un figlio?", "yes", "figlio_morto"),
    ("Hanno mangiato qualcosa di strano?", "yes", "carne_umana"),
    ("La moglie nascondeva qualcosa?", "yes", "bugia"),
    ("L'uomo ha un problema fisico?", "yes", "cieco"),
    ("Il sapore conta?", "yes", "sapore"),
    ("Sono finiti su un'isola?", "yes", "fame"),
    ("Erano su una barca?", "yes", "naufragio"),
]


def build_checks(judge):
    """Collect the checks: stated fact cards from the tests, then the hinted ones.

    Args:
        judge: A `Judge`, for its puzzle and context.

    Returns:
        A list of (context, question, answer, card text, expected decision).
    """
    puzzle = judge.puzzle
    checks = []
    for case in load_tests("gabbiano", "it"):
        # plain yes/no questions only: negations are rewritten before the verifier in the game
        if case["answer"] not in ("yes", "no") or NEGATION.search(case["question"]):
            continue
        context = judge._context(case["history"], case["lit"])
        for card in case["cards"]:
            if card in puzzle.facts and len(checks) < POSITIVE_CHECKS:
                checks.append((context, case["question"], case["answer"], puzzle.card_text[card], True))
    checks += [(judge._context([], []), q, a, puzzle.card_text[card], False) for q, a, card in HINTS]
    return checks


def main():
    """Run every check with every setup and print time, accuracy and changed decisions."""
    judge = Judge(load_puzzle("gabbiano", "it"), make_client())
    checks = build_checks(judge)
    decisions = {}

    print(f"{'setup':<32}{'avg s':>8}{'max s':>8}{'stated ok':>12}{'hints ok':>10}")
    for model, level in SETUPS:
        # same verifier as the game, only the model and the thinking level change
        config = VERIFY_CONFIG.model_copy(update={"thinking_config": types.ThinkingConfig(thinking_level=level)})
        seconds, decisions[model, level] = [], []
        for context, question, answer, card, _ in checks:
            start = time.time()
            contents = f"{context}\n\nQUESTION: {question}\nANSWER: {answer}\nCARD: {card}"
            decisions[model, level].append(json.loads(judge._call(model, contents, config).text)["stated"])
            seconds.append(time.time() - start)
        stated = [d for d, check in zip(decisions[model, level], checks) if check[4]]
        hints = [not d for d, check in zip(decisions[model, level], checks) if not check[4]]
        print(f"{model + ' ' + level:<32}{sum(seconds) / len(seconds):>8.1f}{max(seconds):>8.1f}"
              f"{sum(stated):>8}/{len(stated):<3}{sum(hints):>6}/{len(hints):<3}")

    # decisions that change from the first setup
    first = SETUPS[0]
    for setup in SETUPS[1:]:
        changed = [check for check, a, b in zip(checks, decisions[first], decisions[setup]) if a != b]
        print(f"\n{' '.join(setup)} vs {' '.join(first)}: {len(changed)} decisions changed")
        for _, question, _, card, expected in changed:
            print(f"- {question}  ->  {card}  (should be {'accepted' if expected else 'refused'})")


if __name__ == "__main__":
    main()