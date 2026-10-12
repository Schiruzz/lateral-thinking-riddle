"""HTTP server: serves the game page and runs every question through the chain of `play.py`.

How a game flows:
    1. GET / sends the player to the page, GET /playtest; the page lists the levels from
       GET /api/playtest/riddles.
    2. POST /api/playtest/games starts a game on a riddle: the server keeps a `Play` in
       memory under a random id and returns the story and the sky to draw.
    3. The player speaks or types; the page sends the words to POST /api/playtest/games/{id}/ask
       and gets the sentence to say, the facts found and the false leads closed.

State: games live in memory, so the server runs as a single instance; a restart loses the
games in progress. Every turn is logged as one JSON line, which reaches Cloud Logging.

Run from the repository root:
    uvicorn riddle.server:app --reload
Then open http://localhost:8000.
"""
import json
from datetime import datetime, timezone
from typing import Literal

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from riddle.judge import make_client
from riddle.conductor import OPENING
from riddle.play import Play, load_chain
from riddle.schema import load_index

# playtest: the whole chain on the riddles in the card schema; one chain per riddle, shared by every game on it
PLAYTEST_RIDDLES = load_index()   # the levels, in order: a list of content in puzzles/index.json
MAX_HISTORY = 100   # a longer game is not a real playtest
# a player cannot wait: give up after one retry
CHAINS = {name: load_chain(name, "it", make_client(), max_attempts=2) for name in PLAYTEST_RIDDLES}
PLAYTEST_GAMES = {}   # game id -> Play, kept in memory: the server runs as a single instance

STATIC_DIR = Path(__file__).parent.parent / "static"   # where the page and its scripts live
LOG_FILE = Path("logs/games.jsonl")  # one line per question, kept out of git

app = FastAPI(title="Lateral Thinking Riddle")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")   # the scripts of the pages

MAX_QUESTION_LENGTH = 200  # longer texts are rejected before calling the judge


class PlaytestQuestion(BaseModel):
    """Body of a playtest question: the server keeps the game, the page sends only the words."""
    text: str = Field(max_length=MAX_QUESTION_LENGTH)
    mode: Literal["voice", "text"] = "text"   # how the question was given: transcription errors differ from typos


@app.get("/")
def home():
    """Send the player to the playtest, where the riddles are chosen."""
    return RedirectResponse("/playtest")


@app.get("/playtest")
def playtest_page():
    """Serve the playtest page, static/playtest.html."""
    return FileResponse(STATIC_DIR / "playtest.html")


@app.get("/api/playtest/riddles")
def playtest_riddles():
    """List the riddles the player can choose, in the order of the levels.

    Returns:
        A list of dicts with "id" and "title": nothing of the stories, told only once a game starts.
    """
    return [{"id": name, "title": CHAINS[name]["riddle"].title} for name in PLAYTEST_RIDDLES]

@app.post("/api/playtest/games")
def playtest_new_game(riddle: str = "baita"):
    """Start a playtest game on one riddle.

    Args:
        riddle: The riddle's name, from the page address (`/playtest?riddle=gabbiano`).

    Returns:
        A dict with "id", to send back with every question, "title", "story",
        "opening", the sentence said before the story, and what the page needs to draw the
        sky without knowing any fact: "seed", "figure" (the constellation of what the player
        sees), "stars" (one per fact) and "optional" (how many of them are optional).
    """
    if riddle not in CHAINS:
        raise HTTPException(status_code=404, detail="riddle not found")
    game_id = uuid.uuid4().hex   # random and unguessable, so players cannot touch each other's games
    PLAYTEST_GAMES[game_id] = Play(CHAINS[riddle])
    story = CHAINS[riddle]["riddle"]
    optional = sum(bool(fact.get("optional")) for fact in story.facts.values())
    return {"id": game_id, "title": story.title, "story": story.story, "opening": OPENING,
            "seed": story.id, "figure": story.sky["figure"], "stars": len(story.facts), "optional": optional}


@app.get("/api/playtest/games/{game_id}/solution")
def playtest_solution(game_id: str):
    """Return the truth of the game's riddle, shown when the player decides to stop."""
    play = PLAYTEST_GAMES.get(game_id)
    if play is None:
        raise HTTPException(status_code=404, detail="game not found")
    return {"solution": play.chain["riddle"].truth}


@app.post("/api/playtest/games/{game_id}/ask")
def playtest_ask(game_id: str, question: PlaytestQuestion):
    """Answer one playtest question through the whole chain, and log the turn.

    Args:
        game_id: The id from `playtest_new_game`.
        question: The player's words and how they were given.

        A dict with "reply" (the sentence to say), "answer", "found" (the facts this
        question found, in order of play, each with its "text", whether it was "given" by a
        hint and whether it opens a "sealed" scene), "leads" (the texts of the false leads
        closed for the first time), "questions" (asked so far) and
        "victory"; after a victory also "truth", "next" (the riddle to play next), "sky"
        (the constellation of the truth: figure, name, epithet), "keys" (the texts of the
        key facts, shown bigger) and "remaining" (the texts of the facts not found).
    """
    play = PLAYTEST_GAMES.get(game_id)
    if play is None:
        raise HTTPException(status_code=404, detail="game not found")
    if play.finished:
        raise HTTPException(status_code=400, detail="game over")
    if len(play.history) >= MAX_HISTORY:
        raise HTTPException(status_code=400, detail="game too long")
    history = list(play.history)   # before this question: the labels and the replays need it so
    turn = play.ask(question.text)

    # one log line per turn: the question with its history (a test case), what the player
    # heard, the engine's state and the seconds of each component
    seconds = {key: round(value, 2) for key, value in turn.items() if key.endswith("seconds")}
    entry = json.dumps({"time": datetime.now(timezone.utc).isoformat(), "playtest": True,
                        "puzzle": play.chain["riddle"].id, "game": game_id, "mode": question.mode,
                        "history": history, **turn, **seconds}, ensure_ascii=False)
    print(entry)   # reaches Cloud Logging on Cloud Run
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as log:
        log.write(entry + "\n")

    riddle = play.chain["riddle"]
    found = [{"text": riddle.facts[fact_id]["text"], "given": fact_id in turn["given"],
              "sealed": riddle.scenes[riddle.facts[fact_id]["scene"]]["sealed"]} for fact_id in turn["new"]]
    # a false lead is shown only once the player has asked it: it tells nothing they did not say
    leads = [riddle.exclusions[lead_id]["text"] for lead_id in turn["leads"]]
    response = {"reply": turn["reply"], "answer": turn["answer"], "found": found, "leads": leads,
                "questions": len(play.history), "victory": turn["victory"]}
    if turn["victory"]:
        # the truth comes with the victory: the page tells it once the constellation has changed shape
        position = PLAYTEST_RIDDLES.index(riddle.id)
        response |= {"truth": riddle.truth, "next": PLAYTEST_RIDDLES[(position + 1) % len(PLAYTEST_RIDDLES)],
                     # nothing is left to protect: the page learns the truth's constellation and every fact
                     "sky": {"figure": riddle.sky["truth_figure"], "name": riddle.sky["name"], "epithet": riddle.sky["epithet"]},
                     "keys": [riddle.facts[fact_id]["text"] for fact_id in riddle.key_facts],
                     "remaining": [fact["text"] for fact_id, fact in riddle.facts.items()
                                   if fact_id not in play.session.found and not fact.get("optional")]}
    return response