# Case study: from one LLM judge to a chain that plays the narrator

This is the story of how the game was built, in the order things happened: what was tried, how it was
measured, what the numbers said and what was changed because of them. The README covers how to run it.

## 1. The problem

Lateral thinking riddles ("black stories") are played in pairs: one person knows a strange story, the
other asks yes/no questions until they can explain it. *A man and a woman go into a restaurant. He orders
seagull, takes one bite, goes out and kills himself. Why?*

Playing it with an LLM looks easy and is not:

- **The model knows the solution and the player is trying to extract it.** One careless word gives it
  away, and players try on purpose ("tell me the first word of the solution").
- **Every answer must be true.** A "no" to a question that is half right ends the game for the player,
  who abandons the right track.
- **The questions are messy**: spoken, half-formed, negated ("he didn't know?"), compound, full of
  references to earlier turns.
- **It has to be fun**: a narrator who just says "yes" and "no" is a form, not a game.

The goal set at the start: not a game that works on one riddle, but a system that handles different
riddles with the same structure (a visible situation, a hidden truth), guides the player without giving
the story away, and makes discovering it enjoyable.

## 2. The first prototype: one judge and a clue board

The first version (early October 2026) was built around the seagull riddle.

- **The puzzle as data**: 16 facts written as clue cards, 15 deductions in a tree (two lit cards unlock a
  deduction), the false leads, and the solution as a checklist of key elements.
- **A judge**: `gemini-3.5-flash-lite` with constrained JSON output, answering *yes / no / "yes, but not
  only" / irrelevant / invalid* and proposing the cards the question unlocked.
- **A verifier**: a second, focused call per proposed card, before it is unlocked.
- **Guards in code**: negated questions judged again in positive form; key cards unlocked only when named.

It was measured on hand-labelled questions (full and partial facts, negations, extraction attempts,
spoken phrasing, references to earlier turns), first 112, later 154:

| Version (112 questions) | Answers | Cards | Cards given away | Latency |
|---|---|---|---|---|
| Lite, single judge | 93% | 68% | 41 | 1.2 s |
| + Lite verifier | 92% | 71% | 17 | 1.5 s |
| + Flash verifier | 96% | 89% | 4 | 2.5 s |
| + Flash verifier, low thinking | 93% | 92% | 4 | 2.2 s |
| + negations, solution checks, data fixes | 98% | 92% | 2 | 2.1 s |
| + established context | 96% | 93% | 1 | 2.4 s |
| + links and solution verified without context | 99% | 90% | 3 | 2.2 s |

**Lesson 1: structure beats model size.** The largest gains came from splitting the work (a verifier per
card, guards in code), not from a bigger model.

The judge was then split into an **arbiter** (is the question true?) and a **matcher** (which cards does
it state?), so that each could be tested alone:

| Version (154 questions) | Answers | Cards | Extra cards |
|---|---|---|---|
| Single judge | 99% | 87% | 5 |
| Arbiter / matcher / verifier | 97% | 86% | 13 |
| + two card fixes, trigger words | 98% | 91% | 1 |
| + solution decided by words | 97% | 93% | 1 |
| + arbiter rules from the first playtest | 97% | 92–95% | 1–3 |

Run-to-run noise was 2–3 points, so the split cost nothing measurable and made each part testable.

A first playtest on Cloud Run found what the test set did not: a correct solution typed in plain words
was rejected as "invalid", "Non c'era cibo" answered "No" sounded like the opposite when spoken, and the
microphone picked up the player's comments.

## 3. Why the prototype was abandoned

The numbers were high, but they were the numbers of **one riddle, tuned on its own questions**. Looking
at the puzzle file made the problem obvious: `required_words`, `trigger_words`, `element_words`,
`judge_notes`, hand-written guides. Every fix was a patch for the seagull.

**The generality test.** A second riddle (the cabin: *five friends, a cabin cut off by snow, one of them
found dead in a room locked from inside*) was written with only the fields the arbiter needs, and judged
with the prompts frozen, on 39 real questions from two friends and the author:

- **86% on the 28 clean labels** (3 stable errors, 3 unstable), against 97% on the seagull.
- All the stable errors were generic, not specific to the cabin: the guard on rewritten questions
  rejected accent and typo fixes ("E stato" → "È stato"); "natural causes" was read as "nobody killed
  him" (yes, twice, 3 runs out of 3); a "where should I look" question with a false premise could not
  get a "no".

So the prototype mixed three different jobs in one place (deciding the truth, lighting cards, wording
the reply) and its data was full of riddle-specific fixes. The design was rewritten around one rule:
**the models understand and phrase; the code decides.**

## 4. How it is measured

Before changing the design, the measurement had to be fixed, because 28 clean questions is too few
(one question is worth 3.6 points).

- **The official number comes from real playtests**, per riddle, with its limits stated.
- **For development, simulated players**: `simulate.py` plays the riddle with a model that sees only the
  story and the answers, in five styles taken from the playtest (methodical, laconic, chatty, hasty,
  reckless). Ten games on the cabin gave 189 questions.
- **An automatic labeller** (`labeler.py`, Flash-Lite with high reasoning, instructions written from
  scratch and not shared with the arbiter) labels the simulated questions. Validated on the real cabin
  labels: 28/29 on the clean ones. The author reviews only the disagreements with the arbiter (33 of
  189) plus a random sample (16): 24 were arbiter errors, 9 labeller errors.
- **The arbiter on the simulated questions scored 87%**, consistent with 86% on the real ones: the
  simulated set measures the same thing, with seven times the questions.
- **Fast loop**: during development only the questions a change touches (`--grep`) plus one run on the
  seagull, about 0.10–0.15 €; the full suite (about 0.75 €) only before merging.

Rejected along the way: Flash on Vertex as the labeller (single calls from 2 s to timeouts); Flash-Lite
with low reasoning (it repeated the arbiter's own "natural causes" error).

## 5. The arbiter, rewritten

Two generic fixes first, each measured with three runs:

| Version | Seagull (154) | Cabin simulated (189) | Cabin playtest (28) |
|---|---|---|---|
| Baseline | 97% | 88% (hasty style 68%) | 85% |
| Guard: accents, digits and apostrophes are spelling | 98% | 90% (hasty 86%) | 90% |
| Manner of death: natural, accident, suicide, homicide exclude each other | 97% | questions on the death 60% → 94% | 3/3 |
| Arbiter v2: a specification written from scratch, examples from an invented story, no "partly" | 95% | 95% | 100% |
| v2 + pronouns kept in the rewrite, labels updated | 97% | 94% | 100% |

**Lesson 2: examples from the test set inflate the numbers.** The v1 prompt had examples taken from the
seagull's own questions. v2 uses examples from a riddle no test contains (a pianist who stops playing
mid-concert): the seagull dropped two points and every other set improved.

**Lesson 3: one job per model.** An attempt to have the arbiter also return whether the question was
addressed to the game and which direction it pointed made both tasks worse (the "where should I look"
strategy questions fell to 50%). It was dropped: the arbiter only decides the answer.

The arbiter now reads the truth as prose, then the facts in time order, the victory claims, and a NOT
TRUE line built from the false leads. Its five answers are *yes, no, irrelevant, invalid, unclear*.
With the riddles moved to cards (section 6) the latest numbers are 93% on the cabin playtest, 94% on the
simulated cabin and 97% on the seagull: the playtest drop is one question ("Was there a fireplace?"
answered no, because the room had a stove).

## 6. The riddle as a card

A riddle is a JSON card, and adding one means writing a card, not touching prompts.

- **Facts** are the player's steps, one statement each, in time order, from vague to specific ("Something
  from his past is involved" is a fact). Each has a **role**: *P* (a step, can be given away), *S* (a leap,
  protected) or *C* (the twist, protected).
- **`requires` means "presupposes"**: finding a fact lights everything it presupposes, and a fact is
  *reachable* when what it presupposes is found. Hints are built on this.
- **Scenes**: a *sealed* scene ("years before") opens when one of its facts is found.
- **False leads**, each closed by the fact that rules it out.
- **Victory elements**, in reasoning order and in the player's words ("the chimney was blocked", not
  "the flue was obstructed"), each with the **"why?"** it leaves open.
- **The truth in prose** is separate from the facts: the arbiter needs the complete story, the engine
  needs minimal steps. One list doing both jobs was the reason the old card grew hacks.

Writing the cabin card produced the first **linter rules**, each from a real bug: a fact that stopped
naming the footprints made "were there footprints?" irrelevant; a false lead using the word "poisoned"
made "was he poisoned?" a no. Later: a step the player takes for granted is not a step ("he was already
blind years before", after "he is blind"); a vague fact must not already contain the specific one.

## 7. The matcher and the verifier

The matcher sees only the facts not found yet and quotes the player's words for each one it lights; a
guard checks the quote. The verifier now checks only **key facts** (leaps, twists and what presupposes
them). An ablation on the seagull decided it:

| Matcher on the seagull (1 run) | Exactly right | Extra | Missing | Key extra | Key missing |
|---|---|---|---|---|---|
| Old card, verifier on everything | 75% | 19 | 80 | — | — |
| Verifier on key facts | 86% | 23 | 17 | 1 | 3 |
| No verifier | 84% | 32 | 17 | 5 | 3 |

The verifier prevents 4 of the 5 key facts given away, loses none, and costs 0.1 s on average.

**A rule about "no".** In playtests a "no" to "did he die of natural causes?" lit "it was an accident".
The rule written for it: a "no" states only the negation, never which alternative is true, and never any
part of a compound question; the verifier also checks any fact proposed after a "no".

| | Cabin exact | Seagull exact | Seagull extra | Wrong facts lit by a "no" (simulated) |
|---|---|---|---|---|
| Before | 97% | 85% | 29 | 7 |
| The rule | 95% | 88% | 13 | 4 |
| + verifier after a "no" | 90% | 88% | 13 | 0 |

The price is a few true steps missed after a "no"; it was accepted, because a wrong fact on the board
sends the player down the wrong track.

## 8. The engine and the conductor

**The engine is plain code.** It records the questions, lights facts with what they presuppose, and
decides everything that makes the game feel guided: a repeated question, relief after a long dry spell,
a stall (five questions in a row without a new fact), the victory.

**The conductor writes the sentence the player hears**, and never sees the solution or the facts not
found: it cannot reveal what it does not know. It writes three parts (before, answer, after) and the
code assembles them:

- **The answer may use only the player's words**, plus yes, no, "non" and a few pronouns. Adding one word
  is how a true answer becomes false ("No, the snow covered nothing"), so an answer that fails the check
  is cut to a plain "Yes." or "No.".
- **A reaction appears only for a reason the engine gives** (a repeated question, the victory within
  reach), and is dropped if it names a word of a hidden fact.
- **A joke on an irrelevant question must say that it does not matter**, and may not hide a yes or a no.
- **Fixed lines come from banks written by the author** (relief, stall, relaunch, hint offers): left free,
  the model made puns on the story ("things are starting to breathe") and judgements of importance.

On 189 simulated turns of the cabin: **no lie found**, no reaction dropped, relief seven times and always
after a yes. A turn takes about **2.4 s at the median** (arbiter 0.8, matcher 0.8, conductor 0.8).

## 9. Winning, and being helped

**Victory** was designed from the author's experience of running these games in person. You win with
one sentence, answered yes, that contains every victory element: collecting facts is not enough, the fun
is the synthesis. A partial explanation gets the "why?" of the next element ("Right, but then why did he
kill himself at the restaurant, years later?"), asked once; a "no" to an explanation with a right part
says that part of it is true, without saying which.

On the simulated games the relaunch came once per game at the right moment; "part of it is true" went from
9 times in a row to 3 once it was limited to elements not explained yet.

**Hints.** After a long stall the conductor offers a hint, and gives it only if the player says yes: the
sealed scene before the final phase, the next needed fact in the final phase. A short yes or no is read in
code before the arbiter, because "yes" is not a question about the story. The reconnection to the open
"why?" stays automatic: it is the narrator reminding the question, not a hint.

## 10. Playing it ourselves

A game on the seagull by the author, who knows the story, showed four problems in thirteen questions:

1. He did not know what was missing, asked three times ("what am I missing?"), and the hints never came:
   requests for help are invalid questions and did not count as a stall.
2. The conductor's model offered a hint on its own ("do you need a hint?") that the game could not give.
3. "His wife tricked him", with the context of the game, stated every victory element, but a rule added
   the day before (an element counts only once its facts are found) blocked the victory.
4. Two pairs of facts were the same step said twice ("he is blind" / "he was already blind years before").

The fixes: the victory takes the matcher's judgement again, and the rule stays only where it protects
hidden words; the duplicate steps were merged; the conductor may never offer help on its own; hints are
offered by the engine after a long stall, and given on a yes.

## 11. Tried and dropped

- **A "partly" answer for the arbiter**: it mixed the truth with game design. "Part of it is true" is now
  the engine's decision.
- **Extra fields in the arbiter's output**: interference between tasks (section 5).
- **A hint naming the topic of the next fact**: naming a topic needs words of the hidden fact.
- **Majority vote over three conductor drafts**: it would mostly save irrelevant jokes, at three times the
  cost. Deferred until the playtest shows the plain fallback too often.
- **A confirmation question for doubtful hearing** ("Do you mean...?"): built only if those cases pass
  5% of the turns in voice playtests.
- **Scores and titles**: a riddle is never replayed, and someone who already knows it would solve it in
  a few questions.

## 12. The presentation

The first page was a detective's board with clue cards. The current page is a sky: the narrator is an
eclipse that listens, thinks and speaks; each found fact lights a star of the constellation of what the
player sees (a house, a gull) and clears a veil around it; at the victory the constellation becomes the
one of the truth and takes a mythological name (*Thyestes, the father's banquet*). The sky is drawn on a
canvas and animated with GSAP; the page learns the truth's constellation only with the victory, so the
network never carries the solution early.

## 13. Costs

Gross spend in the first week: about 10 €, covered by credits. Flash-Lite costs about 0.26 € per million
input tokens; a full evaluation suite about 0.75 €, a simulated set of games played through the whole
chain about 0.35 €. Every run is estimated before it is started.

## 14. Limits and next steps

- **The seagull numbers are development numbers**: its card was corrected on its own test questions. The
  cabin is the generality measure, and even there the labels and the card were written by the same person.
- **Next: a third riddle written from scratch** and judged with the prompts frozen, then a real playtest
  with players who do not know the riddles, a linter for the cards, and English.
