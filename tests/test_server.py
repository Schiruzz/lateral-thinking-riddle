"""Checks of the game endpoints with a fake turn: no API calls, no credentials."""

import json

import pytest
from fastapi.testclient import TestClient

import riddle.judge

riddle.judge.make_client = lambda: None   # the server builds its chains at import: no real client in tests
from riddle import server  # noqa: E402  (must come after the patch above)


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A test client whose game log goes to a temporary folder."""
    monkeypatch.setattr(server, "LOG_FILE", tmp_path / "games.jsonl")
    return TestClient(server.app)


def fake_ask(self, question):
    """Stands in for `Play.ask`: a yes that finds the stove and closes the cold, without models."""
    self.history.append((question, "yes"))
    return {"question": question, "positive_question": question, "answer": "yes", "new": ["stufa"],
            "given": [], "leads": ["freddo"], "victory": False, "reply": "Sì.", "seconds": 1.0, "arbiter_seconds": 0.4,
            "matcher_seconds": 0.3, "conductor_seconds": 0.3}


def test_a_playtest_game_starts_on_the_riddle_in_the_address(client):
    game = client.post("/api/playtest/games?riddle=gabbiano").json()
    assert game["title"] == server.CHAINS["gabbiano"]["riddle"].title
    assert game["opening"] == server.OPENING

def test_the_riddles_to_choose_are_the_levels_in_order_with_their_titles(client):
    riddles = client.get("/api/playtest/riddles").json()
    assert [riddle["id"] for riddle in riddles] == server.PLAYTEST_RIDDLES
    assert riddles[0] == {"id": "baita", "title": server.CHAINS["baita"]["riddle"].title}


def test_the_home_page_leads_to_the_playtest(client):
    response = client.get("/", follow_redirects=False)
    assert response.headers["location"] == "/playtest"

def test_an_unknown_riddle_is_not_found(client):
    assert client.post("/api/playtest/games?riddle=nessuno").status_code == 404


def test_a_question_to_an_unknown_game_is_not_found(client):
    assert client.post("/api/playtest/games/nessuna/ask", json={"text": "Nevicava?"}).status_code == 404


def test_a_playtest_turn_returns_the_sentence_and_the_facts_found(client, monkeypatch):
    monkeypatch.setattr(server.Play, "ask", fake_ask)
    game_id = client.post("/api/playtest/games").json()["id"]
    reply = client.post(f"/api/playtest/games/{game_id}/ask", json={"text": "C'era una stufa?"}).json()
    riddle = server.CHAINS["baita"]["riddle"]
    stove = {"text": riddle.facts["stufa"]["text"], "given": False, "sealed": True}   # the stove is in the night
    cold = riddle.exclusions["freddo"]["text"]
    assert reply == {"reply": "Sì.", "answer": "yes", "found": [stove], "leads": [cold], "questions": 1, "victory": False}


def test_a_new_game_draws_the_sky_of_what_is_seen_and_nothing_of_the_truth(client):
    game = client.post("/api/playtest/games").json()
    riddle = server.CHAINS["baita"]["riddle"]
    assert (game["figure"], game["stars"], game["optional"]) == ("house", len(riddle.facts), 2)
    assert "THANATOS" not in json.dumps(game) and "snowflake" not in json.dumps(game)


def test_a_playtest_turn_is_logged_with_the_history_before_it(client, monkeypatch):
    monkeypatch.setattr(server.Play, "ask", fake_ask)
    game_id = client.post("/api/playtest/games").json()["id"]
    for text in ("Nevicava?", "C'era una stufa?"):
        client.post(f"/api/playtest/games/{game_id}/ask", json={"text": text, "mode": "voice"})
    last = json.loads(server.LOG_FILE.read_text(encoding="utf-8").splitlines()[-1])
    assert last["history"] == [["Nevicava?", "yes"]]   # the history before this question, as a test case needs it
    assert (last["puzzle"], last["mode"], last["reply"]) == ("baita", "voice", "Sì.")


def test_the_solution_is_the_truth_of_the_games_riddle(client):
    game_id = client.post("/api/playtest/games?riddle=gabbiano").json()["id"]
    solution = client.get(f"/api/playtest/games/{game_id}/solution").json()
    assert solution == {"solution": server.CHAINS["gabbiano"]["riddle"].truth}


def fake_win(self, question):
    """Stands in for `Play.ask`: the sentence that solves the riddle."""
    self.history.append((question, "yes"))
    self.finished = True
    return {"question": question, "positive_question": question, "answer": "yes", "new": [], "leads": [],
            "victory": True, "reply": "Ce l'hai fatta!", "seconds": 1.0, "arbiter_seconds": 0.4,
            "matcher_seconds": 0.3, "conductor_seconds": 0.3}


def test_a_victory_brings_the_truth_and_the_next_riddle_and_ends_the_game(client, monkeypatch):
    monkeypatch.setattr(server.Play, "ask", fake_win)
    game_id = client.post("/api/playtest/games").json()["id"]
    reply = client.post(f"/api/playtest/games/{game_id}/ask", json={"text": "Tutta la storia"}).json()
    assert reply["sky"] == {"figure": "snowflake", "name": "THANATOS", "epithet": "Il fratello del sonno"}
    assert server.CHAINS["baita"]["riddle"].facts["comignolo"]["text"] in reply["keys"]
    assert reply["next"] == "gabbiano"
    assert client.post(f"/api/playtest/games/{game_id}/ask", json={"text": "Ancora?"}).status_code == 400