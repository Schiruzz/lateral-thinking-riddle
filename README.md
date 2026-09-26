# Lateral Thinking Riddle — an LLM Judge for a Voice Game

[![tests](https://github.com/Schiruzz/lateral-thinking-riddle/actions/workflows/tests.yml/badge.svg)](https://github.com/Schiruzz/lateral-thinking-riddle/actions/workflows/tests.yml)

> Work in progress: the judge is built and evaluated; the playable app comes next.

A lateral thinking puzzle played by voice. The player asks yes/no questions; an LLM
judge answers (yes / no / "yes, but not only" / irrelevant / invalid) and unlocks
hand-written clue cards. Linking two cards unlocks a deduction, and stating the
solution wins. The model never writes what the player sees: it only decides, and
every card it proposes is checked by a second, focused call before it is unlocked.

## Results

Evaluated on 112 hand-labelled test questions: full and partial facts, negations,
extraction attempts, spoken phrasing and references to earlier turns.

| Version | Answers | Cards | Cards given away | Latency |
|---|---|---|---|---|
| Lite, single judge | 93% | 68% | 41 | 1.2 s |
| + Lite verifier | 92% | 71% | 17 | 1.5 s |
| + Flash verifier | 96% | 89% | 4 | 2.5 s |
| + Flash verifier, low thinking | 93% | 92% | 4 | 2.2 s |
| + negations, solution checks, data fixes | 98% | 92% | 2 | 2.1 s |
| + established context | 96% | 93% | 1 | 2.4 s |
| + links and solution verified without context | 99% | 90% | 3 | 2.2 s |

The largest gains came from structure, not from bigger models. The remaining errors
are cards withheld, not given away.

## How it works

- **Puzzle as data**: 16 facts, 15 deductions in a tree, ruled-out leads, and the
  solution as a checklist of key elements.
- **Judge**: `gemini-3.5-flash-lite` with constrained JSON output. It only sees the
  deductions whose two cards are already lit.
- **Verifier**: `gemini-3.5-flash` with low thinking, one yes/no call per proposed
  card, run in parallel.
- **Deterministic guards**: negated questions are judged again in positive form, and
  key cards unlock only when the player names them explicitly.

## Repository

```
puzzles/gabbiano/   it.json (the puzzle as data), tests.it.json (112 labelled questions)
riddle/             puzzle.py (load and check), game.py (game state),
                    judge.py (judge and verifier), evaluate.py (evaluation CLI)
tests/              checks with no API calls: puzzle data, game logic, judge guards
notebooks/          how the judge was built and measured, step by step
```

## Run

```bash
pip install -r requirements.txt
python -m pytest -q          # no API calls
python -m riddle.evaluate    # needs GCP_SA_KEY, see below
```

The evaluation calls Vertex AI. Set `GCP_SA_KEY` to the content of the JSON key
of a Google Cloud service account with the Agent Platform User role.

## Next

A game app with a clue board on Hugging Face Spaces, voice input, an English
version of the puzzle, and more puzzles added as data.
