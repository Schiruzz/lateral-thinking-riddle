"""The mechanical rules of docs/authoring.md, checked on every riddle of the levels: no API calls."""

import re

import pytest

from riddle.puzzle import PUZZLES_DIR
from riddle.schema import load_index, load_riddle

FIGURES_FILE = PUZZLES_DIR.parent / "static" / "figures.js"
LEVELS = load_index()


def figure_names():
    """Return the names of the figures in static/figures.js: the keys of FIGURES, before the atlas helpers."""
    figures = FIGURES_FILE.read_text(encoding="utf-8").split("function atlasCurve")[0]
    return set(re.findall(r"^  (\w+):", figures, re.MULTILINE))


@pytest.fixture(params=LEVELS)
def riddle(request):
    """Every riddle of the levels; loading it already checks that every id exists."""
    return load_riddle(request.param, "it")


def test_every_card_is_a_level():
    """A card left out of puzzles/index.json would never be played."""
    cards = {path.parent.name for path in PUZZLES_DIR.glob("*/arbiter.*.json")}
    assert cards == set(LEVELS)


def test_every_fact_can_be_reached(riddle):
    """Following requires from the facts that need nothing reaches every fact: no cycles, no dead ends."""
    found = set()
    while reachable := riddle.reachable(found):
        found |= set(reachable)
    assert found == set(riddle.facts)


def test_every_scene_has_a_fact_and_every_sealed_scene_a_hint(riddle):
    scenes = {fact["scene"] for fact in riddle.facts.values()}
    for scene_id, scene in riddle.scenes.items():
        assert scene_id in scenes, scene_id
        assert not scene["sealed"] or scene.get("hint"), scene_id


def test_the_victory_needs_a_leap_or_the_final_key_and_not_every_fact(riddle):
    needed = set()
    for element in riddle.victory.values():
        assert element["claim"] and element["why"] and element["requires"], element["id"]
        needed |= riddle.closure(element["requires"])
    assert any(riddle.facts[fact_id]["role"] in ("S", "C") for fact_id in needed)
    assert needed < set(riddle.facts)


def test_the_story_ends_with_its_question(riddle):
    assert riddle.story.rstrip().endswith("?")


def test_both_figures_exist(riddle):
    names = figure_names()
    assert riddle.sky["figure"] in names and riddle.sky["truth_figure"] in names