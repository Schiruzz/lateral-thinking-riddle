"""Simulated players: a model plays the puzzle against the real arbiter, to collect questions.

The player sees only the visible situation and the answers it gets, never the
truth. Five styles copy what real players did in the playtest. Every question
is logged in the playtest's format, so the same tools label it; the numbers
from simulated games guide development and are never reported as results.

Run from the repository root:
    python -m riddle.simulate --puzzle baita --games 2
"""

import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from google.genai import types

from riddle.judge import UNCLEAR, YES, Judge, make_client
from riddle.puzzle import load_arbiter

PLAYER_MODEL = "gemini-3.5-flash-lite"   # it only has to play in different ways, not to be clever
MAX_QUESTIONS = 25
ANSWER_TEXT = {"yes": "Sì", "no": "No", "partly": "Sì, ma non solo", "irrelevant": "Non importa",
               "invalid": "Domanda non valida", "unclear": "Non ho capito"}   # what a player reads on the page

PLAYER_PROMPT = """You play a lateral thinking puzzle as a player. You know only the situation below. A host
who knows the hidden truth answers each of your questions with one of: "Sì", "No",
"Non importa", "Sì, ma non solo", "Domanda non valida", "Non ho capito".

Your goal is to find out what really happened. Ask one question at a time, in Italian,
the way a real person would. Use the answers you get: do not fix on one idea and ignore
them. When you think you know the whole story, state your explanation in one sentence
and set is_explanation to true.

YOUR STYLE: {style}

SITUATION: {story}

OUTPUT
- question: your next question or statement, exactly as you would say or type it
- is_explanation: true only when it states your full explanation of what happened"""

# styles taken from what real players did in the playtest
STYLES = {
    "methodical": "Clear, complete yes/no questions. Start from the obvious explanation the situation "
                  "suggests, rule it out, then go step by step from general to specific.",
    "laconic": "Very short questions, often fragments that continue your previous one "
               "(\"E prima?\", \"Con le mani?\"). Rarely more than four words.",
    "spoken": "You talk as if speaking aloud: fillers (allora, tipo, quindi, ehm), statements instead of "
              "questions (\"secondo me era geloso\"), sometimes negated questions (\"non era da solo, vero?\").",
    "hasty": "You type fast on a phone: typos, missing accents (\"e stato\", \"perche\"), numbers as digits, "
             "often no question mark.",
    "reckless": "You jump to bold hypotheses early, ask questions that assume things not yet established "
                "(\"devo capire chi l'ha tradito?\"), and sometimes ask about the game itself "
                "(\"sono vicino?\", \"questa parte conta?\").",
}

PLAYER_SCHEMA = {
    "type": "OBJECT",
    "properties": {"question": {"type": "STRING"}, "is_explanation": {"type": "BOOLEAN"}},
    "required": ["question", "is_explanation"],
    "propertyOrdering": ["question", "is_explanation"],
}


def play(judge, puzzle_name, style, max_questions=MAX_QUESTIONS):
    """Play one game with a simulated player against the arbiter.

    Args:
        judge: A `Judge` built on a puzzle from `load_arbiter`.
        puzzle_name: Folder name of the puzzle, written in the log.
        style: A key of `STYLES`.
        max_questions: The game stops here if the player has not solved it.

    Returns:
        One log row per question, in the playtest's format plus "persona"
        and "is_explanation".
    """
    config = types.GenerateContentConfig(
        system_instruction=PLAYER_PROMPT.format(style=STYLES[style], story=judge.puzzle.story),
        temperature=1.0,   # variety between games matters more than consistency here
        response_mime_type="application/json", response_schema=PLAYER_SCHEMA)
    game = uuid.uuid4().hex
    exchanges = []   # (player's words, answer): what the player sees, unclear questions included
    history = []     # (positive question, answer): what the arbiter gets, as in the game
    rows = []
    for _ in range(max_questions):
        seen = "\n".join(f"- {q} -> {ANSWER_TEXT[a]}" for q, a in exchanges) or "- none"
        # the judge's call brings the same client and retries on rate limits
        move = json.loads(judge._call(PLAYER_MODEL, f"YOUR QUESTIONS SO FAR:\n{seen}\n\nYour next move:", config).text)
        verdict = judge.answer(move["question"], history, [])
        rows.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "simulated": True,
            "puzzle": puzzle_name,
            "game": game,
            "persona": style,
            "mode": "simulated",
            "question": move["question"],
            "history": list(history),   # the exchanges before this question
            "positive_question": verdict["positive_question"],
            "answer": verdict["answer"],
            "is_explanation": move["is_explanation"],
        })
        exchanges.append((move["question"], verdict["answer"]))
        # as in the game, an unclear question does not count as an exchange
        if verdict["answer"] != UNCLEAR:
            history.append((verdict["positive_question"], verdict["answer"]))
        if move["is_explanation"] and verdict["answer"] == YES:
            break
    return rows


def main():
    """Play the games, append them to the log and print one line per game."""
    parser = argparse.ArgumentParser(description="Play simulated games against the arbiter.")
    parser.add_argument("--puzzle", default="baita")
    parser.add_argument("--language", default="it")
    parser.add_argument("--games", type=int, default=2, help="games per style")
    args = parser.parse_args()

    judge = Judge(load_arbiter(args.puzzle, args.language), make_client())
    log_file = Path(f"logs/simulated.{args.puzzle}.jsonl")
    log_file.parent.mkdir(exist_ok=True)
    for style in STYLES:
        for _ in range(args.games):
            rows = play(judge, args.puzzle, style)
            # append each game as soon as it ends: a crash later does not lose it
            with log_file.open("a", encoding="utf-8") as log:
                log.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
            solved = rows[-1]["is_explanation"] and rows[-1]["answer"] == YES
            print(f"{style:<11} {len(rows):>2} questions  {'solved' if solved else 'not solved'}")
    print(f"log: {log_file}")


if __name__ == "__main__":
    main()