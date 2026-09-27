"""HTTP server: serves the game page and exposes the judge to it.

How a game flows:
    1. The browser loads the page from GET /.
    2. The page calls POST /api/games: the server creates a Game, keeps it in
       memory under a random id, and returns the id and the story to read aloud.
    3. The player speaks; the browser transcribes the voice to text and calls
       POST /api/games/{id}/ask with that text.
    4. The server asks the judge, lights the confirmed cards in the Game, and
       returns the answer, the new cards and the whole board, so the page only
       has to draw what it receives.

State: games live in the GAMES dict, in the memory of this process. This is
enough for a demo that runs as a single server instance; if the server
restarts, the games in progress are lost.

Run from the repository root:
    uvicorn riddle.server:app --reload
Then open http://localhost:8000 (the page) or http://localhost:8000/docs
(an automatic page to try the endpoints by hand).
"""
import json
import time
from datetime import datetime, timezone

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from riddle.game import Game
from riddle.judge import UNCLEAR, Judge, make_client
from riddle.puzzle import load_puzzle

# loaded once when the server starts, shared by every game
PUZZLE = load_puzzle("gabbiano", "it")
JUDGE = Judge(PUZZLE, make_client())      # needs GCP_SA_KEY in the environment
STATIC_DIR = Path(__file__).parent.parent / "static"   # where index.html lives
LOG_FILE = Path("logs/games.jsonl")  # one line per question, kept out of git
GAMES = {}   # game id -> Game, kept in memory: the server runs as a single instance

app = FastAPI(title="Lateral Thinking Riddle")

MAX_QUESTION_LENGTH = 200  # longer texts are rejected before calling the judge


class Question(BaseModel):
    """Body of an ask request: the question as the player said or typed it."""
    text: str = Field(max_length=MAX_QUESTION_LENGTH)


def card_view(card):
    """Return what the page needs to draw a card.

    Args:
        card: The id of a card.

    Returns:
        A dict with "id", "text" (shown on the card), "zone" ("restaurant" or
        "past") and "kind": "fact", "deduction", "theory" or "ruled_out", so
        the page can place and style each card.
    """
    if card in PUZZLE.facts:
        kind = "fact"
    elif card in PUZZLE.exclusions:
        kind = "ruled_out"
    elif card in PUZZLE.theories:
        kind = "theory"
    else:
        kind = "deduction"
    return {"id": card, "text": PUZZLE.card_text[card], "zone": PUZZLE.card_zone[card], "kind": kind}


def board_view(game):
    """Return the board as the page draws it, without revealing cards not found yet.

    Threads and guides point to cards the player has not unlocked: their ids
    would give the answer away to anyone reading the network traffic, so only
    the lit cards they link, their zone and their question are sent.

    Args:
        game: The `Game` to draw.

    Returns:
        A dict with "cards" and "ruled_out" (card views), "past_open",
        "threads" (each with "cards", "zone", "theory", "final", "question")
        and "guides" (each with "zone" and "question").
    """
    board = game.board()
    return {
        "cards": [card_view(c) for c in board["cards"]],
        "ruled_out": [card_view(c) for c in board["ruled_out"]],
        "past_open": board["past_open"],
        "threads": [{"cards": t["cards"], "zone": t["zone"], "theory": t["theory"],
                     "final": t["id"] == PUZZLE.root, "question": t["question"]} for t in board["threads"]],
        "guides": [{"zone": g["zone"], "question": g["question"]} for g in board["guides"]],
    }

@app.get("/")
def page():
    """Serve the game page, static/index.html."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/games")
def new_game():
    """Start a new game.

    Returns:
        A dict with "id", to send back with every question of this game,
        "title", "story", the text the page reads to the player at the start,
        and "board", the starting board with the first guide questions.
    """
    game_id = uuid.uuid4().hex   # random and unguessable, so players cannot touch each other's games
    game = Game(PUZZLE)
    GAMES[game_id] = game
    return {"id": game_id, "title": PUZZLE.title, "story": PUZZLE.story, "board": board_view(game)}


@app.post("/api/games/{game_id}/ask")
def ask(game_id: str, question: Question):
    """Judge one question of the player and update the game.

    Args:
        game_id: The id returned by /api/games.
        question: The player's words.

    Returns:
        A dict with:
            "positive_question": the question as the judge understood it,
                shown or read back so the player hears what was understood;
            "answer": one of the answer ids (yes, no, partly, irrelevant, invalid);
            "new_cards": the cards lit by this question, to announce them;
            "board": the board to draw, from `board_view`;
            "score": the points earned so far;
            "won": True once the solution is lit.

    Raises:
        HTTPException: 404 if the game id is unknown, e.g. after a server restart.
    """
    game = GAMES.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")

    # the judge sees the conversation so far and the lit cards, then decides
    start = time.perf_counter()
    verdict = JUDGE.judge(question.text, game.history, game.lit)
    latency = time.perf_counter() - start
    # remember the exchange as context, unless the judge did not understand it: that does not count as a question
    if verdict["answer"] != UNCLEAR:
        game.history.append((verdict["positive_question"], verdict["answer"]))
    # light the confirmed cards and, in chain, the cards they imply
    new_cards = game.unlock(verdict["cards"])

    # append this question to the game log: enough to replay it and to measure the judge
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(json.dumps({
            "time": datetime.now(timezone.utc).isoformat(),
            "game": game_id,
            "question": question.text,
            "positive_question": verdict["positive_question"],
            "answer": verdict["answer"],
            "new_cards": new_cards,
            "score": game.score,
            "won": game.won(),
            "latency": round(latency, 2),
        }, ensure_ascii=False) + "\n")

    return {
        "positive_question": verdict["positive_question"],
        "answer": verdict["answer"],
        "new_cards": [card_view(card) for card in new_cards],
        "board": board_view(game),
        "score": game.score,
        "won": game.won(),
        "questions": len(game.history),                              # questions asked so far
        "solution": PUZZLE.solution if game.won() else None,         # revealed only once the case is solved
    }