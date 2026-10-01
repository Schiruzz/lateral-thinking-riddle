"""Trial: the full pipeline, arbiter then card matcher then verifier, on the test questions.

The arbiter only answers (see arbiter_trial). The matcher reads the question
and the answer already decided and proposes cards, without seeing the solution.
The verifier and the code guards are the judge's. The report is the same as
evaluate's, plus the time and input tokens of each step. The game does not use this file.

Run from the repository root:
    python -m riddle.pipeline_trial
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor

from google.genai import types

from riddle.arbiter_trial import answer, arbiter_config
from riddle.evaluate import report
from riddle.judge import INVALID, IRRELEVANT, JUDGE_MODEL, UNCLEAR, YES, Judge, make_client, normalize
from riddle.puzzle import load_puzzle, load_tests

MATCHER_STEPS = """HOW TO FIND THE CARDS
1. For every card, first write in "quote" the exact words of the question that state it.
2. Fact cards: return one only if the quote, with the answer, states every element of the card: if a person, place, time or reason is missing, return no card. Being about the same topic is not enough.
3. Deduction cards: only after yes, and only if the player's words alone state the whole deduction.
4. Exclusion cards: return one when the answer rules out that false lead entirely; quote the words that state the false lead.
5. Solution elements: only after yes, and only those the question states entirely.
6. Use the context only to resolve references (pronouns, "lì", "l'ha ordinato").
"""


def matcher_config(judge, lit):
    """Build the matcher's config: the cards the player can unlock now, with their criteria.

    Args:
        judge: A `Judge`, for its puzzle and its card lists.
        lit: Ids of the cards already lit, which decide the reachable deductions.

    Returns:
        A `GenerateContentConfig` whose schema only accepts the cards reachable now.
    """
    puzzle = judge.puzzle
    reachable = puzzle.reachable_deductions(lit)
    deduction_lines = "\n".join(f"- {d_id}: {text}" for d_id, text in reachable) or "- none"
    prompt = f"""You find which cards a player's question has unlocked in a lateral thinking
puzzle played by voice. The question has already been answered: you do not judge whether
it is true, you only read what the player's words, together with that answer, establish.

FACT CARDS: return one when the question, with its answer, states the whole fact (id: fact):
{judge.fact_lines}

DEDUCTION CARDS the player can reach now: return one only after yes, when the player's words state the whole deduction (id: deduction):
{deduction_lines}

EXCLUSION CARDS: false leads; return one when the answer rules it out entirely (id: false lead):
{judge.exclusion_lines}

SOLUTION ELEMENTS: list one only after yes, when the question states it entirely (id: element):
{judge.element_lines}

{MATCHER_STEPS}"""
    card_ids = sorted(set(puzzle.facts) | set(puzzle.exclusions) | {d_id for d_id, _ in reachable})
    schema = {
        "type": "OBJECT",
        "properties": {
            "cards": {"type": "ARRAY", "items": {
                "type": "OBJECT",
                "properties": {"quote": {"type": "STRING"}, "id": {"type": "STRING", "enum": card_ids}},
                "required": ["quote", "id"],
                "propertyOrdering": ["quote", "id"],
            }},
            "solution_elements": {"type": "ARRAY", "items": {"type": "STRING", "enum": list(puzzle.solution_elements)}},
        },
        "required": ["cards", "solution_elements"],
        "propertyOrdering": ["cards", "solution_elements"],
    }
    return types.GenerateContentConfig(system_instruction=prompt, temperature=0,
                                       response_mime_type="application/json", response_schema=schema)


def find_cards(judge, question, verdict, history, lit):
    """Find the cards a judged question unlocks: matcher, code guards, then verifier.

    Args:
        judge: A `Judge`, for its calls, context, verifier and puzzle.
        question: The player's words.
        verdict: The arbiter's verdict, with "positive_question" and "answer".
        history: (positive question, answer) pairs of the game so far.
        lit: Ids of the cards already lit.

    Returns:
        The ids of the cards to unlock, with the root when the solution is won,
        and the input tokens of the matcher call.
    """
    puzzle = judge.puzzle
    answer_id = verdict["answer"]
    context = judge._context(history, lit)
    contents = (f"{context}\n\nPLAYER'S WORDS: {question}\n"
                f"QUESTION: {verdict['positive_question']}\nANSWER: {answer_id}")
    response = judge._call(JUDGE_MODEL, contents, matcher_config(judge, lit))
    match = json.loads(response.text)

    # the same guards as the judge: quotes in the player's words, key words, exclusions unverified
    said = normalize(f"{question} {verdict['positive_question']}")
    candidates = [c["id"] for c in match["cards"] if normalize(c["quote"]) in said]
    required = puzzle.required_words
    candidates = [card for card in candidates
                  if card not in required or any(w in question.lower() for w in required[card])]
    exclusions = [card for card in candidates if card in puzzle.exclusions]
    to_verify = [card for card in candidates if card not in puzzle.exclusions]
    final = puzzle.is_reachable(puzzle.root, lit)
    elements = list(puzzle.solution_elements) if final and answer_id == YES and match["solution_elements"] else []

    # facts may use the context for references; deductions and the solution must be in the player's words
    checks_to_run = [(puzzle.card_text[card], context if card in puzzle.facts else judge.no_context)
                     for card in to_verify]
    checks_to_run += [(puzzle.solution_elements[e], judge.no_context) for e in elements]
    with ThreadPoolExecutor() as pool:
        checks = list(pool.map(lambda item: judge.verify(item[0], verdict["positive_question"], answer_id, item[1]),
                               checks_to_run))
    card_checks, element_checks = checks[:len(to_verify)], checks[len(to_verify):]

    cards = exclusions + [card for card, ok in zip(to_verify, card_checks) if ok]
    if elements and all(element_checks):
        cards.append(puzzle.root)
    return cards, response.usage_metadata.prompt_token_count


def main():
    """Run the full pipeline on every test question and print evaluate's report, plus time and tokens per step."""
    puzzle = load_puzzle("gabbiano", "it")
    judge = Judge(puzzle, make_client())
    tests = load_tests("gabbiano", "it")
    config = arbiter_config(puzzle)

    rows, arbiter_tokens, matcher_tokens = [], [], []
    arbiter_seconds, cards_seconds = [], []   # time of each step, to see which one is slow
    for i, case in enumerate(tests, 1):
        print(f"\rpipeline: {i}/{len(tests)}", end="", flush=True)
        known = puzzle.closure(case["lit"])
        start = time.time()
        verdict, tokens = answer(judge, config, case["question"], case["history"], case["lit"])
        arbiter_seconds.append(time.time() - start)
        arbiter_tokens.append(tokens)
        cards = []
        # questions without a real answer unlock nothing: no matcher call
        if verdict["answer"] not in (IRRELEVANT, INVALID, UNCLEAR):
            cards_start = time.time()
            cards, tokens = find_cards(judge, case["question"], verdict, case["history"], case["lit"])
            cards_seconds.append(time.time() - cards_start)
            matcher_tokens.append(tokens)
        rows.append({
            "group": case["group"], "question": case["question"], "rewritten": verdict["positive_question"],
            "expected_answer": case["answer"], "answer": verdict["answer"],
            "expected_cards": puzzle.closure(case["cards"]) - known,
            "cards": puzzle.closure(cards) - known,
            "seconds": time.time() - start,
        })
    print()
    report(rows)
    # average and worst case of each step: a high maximum means retries on rate limits or timeouts
    print(f"\n{'step':<10}{'avg s':>8}{'max s':>8}{'avg tokens':>12}")
    for name, seconds, tokens in (("arbiter", arbiter_seconds, arbiter_tokens), ("cards", cards_seconds, matcher_tokens)):
        print(f"{name:<10}{sum(seconds) / len(seconds):>8.1f}{max(seconds):>8.1f}{sum(tokens) / len(tokens):>12.0f}")


if __name__ == "__main__":
    main()
