"""Turn the playtest log into test cases for the arbiter, labelled blind.

Two steps, run from the repository root:
    1. python -m riddle.playtest_labels export --since 2026-10-05T10:00:00Z
       writes logs/labels.baita.json: every question, game by game, without the
       judge's answers. Fill "answer" by hand; leave it empty to drop a question.
    2. python -m riddle.playtest_labels build
       joins the labels with the logged history into puzzles/baita/tests.it.json.
"""

import argparse
import json
from pathlib import Path

from riddle.puzzle import ANSWERS, PUZZLES_DIR

LOG_FILE = Path("logs/playtest.baita.json")   # from: gcloud logging read 'jsonPayload.playtest=true' --format json
LABEL_FILE = Path("logs/labels.baita.json")
TESTS_FILE = PUZZLES_DIR / "baita" / "tests.it.json"


def read_log():
    """Return the logged playtest questions, oldest first.

    Returns:
        One dict per question: the fields printed by the server, plus the
        "timestamp" added by Cloud Logging, which identifies the question.
    """
    entries = json.loads(LOG_FILE.read_text(encoding="utf-8"))
    rows = [{**e["jsonPayload"], "timestamp": e["timestamp"]} for e in entries]
    return sorted(rows, key=lambda row: row["timestamp"])   # gcloud returns the newest first


def export(since):
    """Write the questions to label, without the judge's answers.

    Args:
        since: UTC time the link was sent, e.g. "2026-10-05T10:00:00Z": games
            started before it are the author's own tries.
    """
    # never overwrite labels already written by hand
    if LABEL_FILE.exists():
        raise SystemExit(f"{LABEL_FILE} already exists: delete it to export again")

    # questions grouped by game, so each one comes after the questions it may refer to
    games = {}
    for row in read_log():
        games.setdefault(row["game"], []).append(row)

    labels = []
    for rows in games.values():
        # same timestamp format on both sides, so comparing the strings compares the times
        source = "playtest" if rows[0]["timestamp"] >= since else "author"
        for row in rows:
            labels.append({"timestamp": row["timestamp"], "source": source, "game": row["game"][:8],
                           "question": row["question"], "answer": "", "note": ""})

    LABEL_FILE.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    playtest = sum(label["source"] == "playtest" for label in labels)
    print(f"games:     {len(games)}")
    print(f"questions: {len(labels)} ({playtest} playtest, {len(labels) - playtest} author)")
    print(f"labels to fill in: {LABEL_FILE}")


def build():
    """Join the labels with the logged history and write the test cases."""
    labels = json.loads(LABEL_FILE.read_text(encoding="utf-8"))
    by_time = {row["timestamp"]: row for row in read_log()}

    tests = []
    for label in labels:
        if not label["answer"]:
            continue   # left empty on purpose: not a real question
        if label["answer"] not in ANSWERS:
            raise SystemExit(f"unknown answer {label['answer']!r} for: {label['question']}")
        row = by_time[label["timestamp"]]
        # one group per source, and per mode for friends: transcription errors differ from typos
        group = "author" if label["source"] == "author" else f"playtest_{row.get('mode', 'text')}"
        # doubtful labels (note starting with "?") are counted apart: a miss there is not a clear error
        if label["note"].startswith("?"):
            group += "_doubtful"
        tests.append({"group": group, "question": row["question"], "answer": label["answer"],
                      "cards": [], "lit": [], "history": row["history"]})

    TESTS_FILE.write_text(json.dumps(tests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"test cases: {len(tests)} -> {TESTS_FILE}")


def main():
    """Parse the command line and run one of the two steps."""
    parser = argparse.ArgumentParser(description="Turn the playtest log into labelled test cases.")
    steps = parser.add_subparsers(dest="step", required=True)
    export_parser = steps.add_parser("export", help="write the questions to label")
    export_parser.add_argument("--since", required=True, help="UTC time the link was sent, e.g. 2026-10-05T10:00:00Z")
    steps.add_parser("build", help="write puzzles/baita/tests.it.json from the labels")
    args = parser.parse_args()

    if args.step == "export":
        export(args.since)
    else:
        build()


if __name__ == "__main__":
    main()