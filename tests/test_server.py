"""Checks of the ask stream with a fake judge: no API calls, no credentials."""

import json

import pytest
from fastapi.testclient import TestClient

import riddle.judge

riddle.judge.make_client = lambda: None   # the server builds its judge at import: no real client in tests
from riddle import server  # noqa: E402  (must come after the patch above)


class FakeJudge:
    """Stands in for the server's judge: answers yes and returns fixed cards, or fails on the cards."""

    def __init__(self, card_ids=(), fail=False):
        self.card_ids = list(card_ids)
        self.fail = fail
        self.cards_history = None   # the history the cards step received

    def answer(self, question, history, lit):
        return {"positive_question": question, "answer": "yes"}

    def cards(self, question, verdict, history, lit):
        self.cards_history = list(history)
        if self.fail:
            raise RuntimeError("cards step down")
        return self.card_ids


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A test client whose game log goes to a temporary folder."""
    monkeypatch.setattr(server, "LOG_FILE", tmp_path / "games.jsonl")
    return TestClient(server.app)


def ask(client, text):
    """Start a game, ask one question; return the game id and the parsed stream lines."""
    game_id = client.post("/api/games").json()["id"]
    response = client.post(f"/api/games/{game_id}/ask", json={"text": text})
    return game_id, [json.loads(line) for line in response.text.splitlines()]


def test_answer_comes_first_then_the_board(client, monkeypatch):
    """Line 1 holds only the answer; line 2 the cards and the board."""
    judge = FakeJudge(card_ids=["cieco"])
    monkeypatch.setattr(server, "JUDGE", judge)
    game_id, lines = ask(client, "Era cieco?")

    assert lines[0] == {"positive_question": "Era cieco?", "answer": "yes"}
    assert [card["id"] for card in lines[1]["new_cards"]] == ["cieco"]
    assert judge.cards_history == []                                  # the cards see the history before this question
    assert server.GAMES[game_id].history == [("Era cieco?", "yes")]   # then the exchange is remembered


def test_cards_failure_becomes_an_error_line(client, monkeypatch):
    """If the cards fail, line 2 says so and the answered question stays in the history."""
    monkeypatch.setattr(server, "JUDGE", FakeJudge(fail=True))
    game_id, lines = ask(client, "Era cieco?")

    assert lines[0]["answer"] == "yes"
    assert lines[1] == {"error": "cards_failed"}
    assert server.GAMES[game_id].history == [("Era cieco?", "yes")]