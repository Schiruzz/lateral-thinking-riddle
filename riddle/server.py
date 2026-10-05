"""HTTP server: serves the game page and exposes the judge to it.

How a game flows:
    1. The browser loads the page from GET /.
    2. The page calls POST /api/games: the server creates a Game, keeps it in
       memory under a random id, and returns the id and the story to read aloud.
    3. The player speaks; the browser transcribes the voice to text and calls
       POST /api/games/{id}/ask with that text.
    4. The server asks the judge and streams two JSON lines (NDJSON): first the
       answer, as soon as it is known, so the page can speak it at once; then
       the new cards, the whole board and the score, so the page only has to
       draw what it receives. If the cards fail, the second line is an error.

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
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from riddle.game import Game
from riddle.judge import UNCLEAR, Judge, make_client
from riddle.puzzle import load_arbiter, load_puzzle

# loaded once when the server starts, shared by every game
PUZZLE = load_puzzle("gabbiano", "it")
JUDGE = Judge(PUZZLE, make_client(), max_attempts=2)   # a player cannot wait: give up after one retry; needs GCP_SA_KEY

# playtest: the arbiter alone on a puzzle without cards, to collect real questions
PLAYTEST = load_arbiter("baita", "it")
PLAYTEST_JUDGE = Judge(PLAYTEST, make_client(), max_attempts=2)
MAX_HISTORY = 100   # a longer game is not a real playtest

STATIC_DIR = Path(__file__).parent.parent / "static"   # where index.html lives
LOG_FILE = Path("logs/games.jsonl")  # one line per question, kept out of git
GAMES = {}   # game id -> Game, kept in memory: the server runs as a single instance

app = FastAPI(title="Lateral Thinking Riddle")

MAX_QUESTION_LENGTH = 200  # longer texts are rejected before calling the judge


class Question(BaseModel):
    """Body of an ask request: the question as the player said or typed it."""
    text: str = Field(max_length=MAX_QUESTION_LENGTH)


class PlaytestQuestion(BaseModel):
    """Body of a playtest request: the page keeps the game, so it sends everything each time."""
    game: str = Field(max_length=40)   # random id made by the page, groups the log lines of one game
    text: str = Field(max_length=MAX_QUESTION_LENGTH)
    history: list[tuple[str, str]] = Field(default_factory=list, max_length=MAX_HISTORY)


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
    """Judge one question of the player and update the game, streaming the result in two lines.

    Args:
        game_id: The id returned by /api/games.
        question: The player's words.

    Returns:
        A stream of two JSON lines (NDJSON):
            1. "positive_question", the question as the judge understood it,
               and "answer", one of the answer ids;
            2. "new_cards" (card views lit by this question), "board" (from
               `board_view`), "score", "won", "questions" (asked so far) and
               "solution" (only once won); or {"error": "cards_failed"}.

    Raises:
        HTTPException: 404 if the game id is unknown, e.g. after a server restart.
    """
    game = GAMES.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")

    # the answer is decided before the stream opens: if it fails, the page gets a plain HTTP error
    start = time.perf_counter()
    verdict = JUDGE.answer(question.text, game.history, game.lit)
    answer_seconds = time.perf_counter() - start
    history = list(game.history)   # the exchanges before this question: the cards' context
    # remember the exchange, unless the judge did not understand it: that does not count as a question
    if verdict["answer"] != UNCLEAR:
        game.history.append((verdict["positive_question"], verdict["answer"]))

    def stream():
        # line 1: the answer, sent at once so the page can speak it while the cards are decided
        yield json.dumps({"positive_question": verdict["positive_question"],
                          "answer": verdict["answer"]}, ensure_ascii=False) + "\n"

        start = time.perf_counter()
        try:
            card_ids = JUDGE.cards(question.text, verdict, history, game.lit)
        except Exception as e:   # the stream is already open: report the failure as the second line
            print(f"[error] cards failed: {e!r}")
            yield json.dumps({"error": "cards_failed"}) + "\n"
            return
        cards_seconds = time.perf_counter() - start
        # light the confirmed cards and, in chain, the cards they imply
        new_cards = game.unlock(card_ids)

        # one log line per question: enough to replay it and to measure each step;
        # printed too, so on Cloud Run it reaches Cloud Logging (the container's files are lost on restart)
        entry = json.dumps({
            "time": datetime.now(timezone.utc).isoformat(),
            "game": game_id,
            "question": question.text,
            "positive_question": verdict["positive_question"],
            "answer": verdict["answer"],
            "new_cards": new_cards,
            "score": game.score,
            "won": game.won(),
            "answer_seconds": round(answer_seconds, 2),
            "cards_seconds": round(cards_seconds, 2),
        }, ensure_ascii=False)
        print(entry)
        LOG_FILE.parent.mkdir(exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as log:
            log.write(entry + "\n")

        # line 2: what the page draws
        yield json.dumps({
            "new_cards": [card_view(card) for card in new_cards],
            "board": board_view(game),
            "score": game.score,
            "won": game.won(),
            "questions": len(game.history),
            "solution": PUZZLE.solution if game.won() else None,   # revealed only once the case is solved
        }, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")



@app.get("/playtest")
def playtest_page():
    """Serve the playtest page, static/playtest.html."""
    return FileResponse(STATIC_DIR / "playtest.html")


@app.get("/api/playtest")
def playtest_story():
    """Return the title and the story of the playtest puzzle, never the solution."""
    return {"title": PLAYTEST.title, "story": PLAYTEST.story}


@app.get("/api/playtest/solution")
def playtest_solution():
    """Return the solution, shown when the player decides to stop."""
    return {"solution": PLAYTEST.solution}


@app.post("/api/playtest/ask")
def playtest_ask(question: PlaytestQuestion):
    """Answer one playtest question with the arbiter alone, and log it.

    The server keeps nothing: the page sends the history of its game, as
    (positive question, answer) pairs, and adds this exchange to it unless
    the answer is unclear, as in the game.

    Args:
        question: The game id, the player's words and the history so far.

    Returns:
        A dict with "positive_question" and "answer".
    """
    start = time.perf_counter()
    verdict = PLAYTEST_JUDGE.answer(question.text, question.history, [])   # no cards, nothing lit
    answer_seconds = time.perf_counter() - start

    # one log line per question, with its history: enough to turn it into a test case
    entry = json.dumps({
        "time": datetime.now(timezone.utc).isoformat(),
        "playtest": True,
        "puzzle": "baita",
        "game": question.game,
        "question": question.text,
        "history": question.history,
        "positive_question": verdict["positive_question"],
        "answer": verdict["answer"],
        "answer_seconds": round(answer_seconds, 2),
    }, ensure_ascii=False)
    print(entry)   # reaches Cloud Logging on Cloud Run
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(entry + "\n")

    return {"positive_question": verdict["positive_question"], "answer": verdict["answer"]}