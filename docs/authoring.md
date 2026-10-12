# Writing a riddle

A riddle is a card: `puzzles/<id>/arbiter.<language>.json`. Adding one means writing the card,
never touching prompts or engine code. This file holds the judgement rules; the mechanical ones
are checked by the tests (last section). Each rule has a good example and a counterexample from
real cards; a new riddle adds an example only when it shows a mistake no rule covered yet.

## Workflow

1. Choose the story (section 1) and analyse it: scenes, leaps, the final key, false leads.
2. Write the facts in order of play, then exclusions, victory, scene hints, sky.
3. Check the card against this file, then run `python -m pytest -q`.
4. Add the riddle to `puzzles/index.json`; add its figures to `static/figures.js` if missing.
5. Measure it with the frozen system: `simulate`, `labeler`, review, `build`.

## 1. The story

### What makes a riddle
The visible story holds an **anomaly**: things that do not fit together (light and death, frost
in summer, a "thank you" after a gun). The truth is the simplest story that makes them fit. The
player starts from the obvious answer the text suggests and reaches the truth one fact at a time.

### Families
- **Deaths hard to explain**: the cause rests on common knowledge few people think of.
  Baita (carbon monoxide), il cubo (ice that melts).
- **Tragic true stories turned into a game or a metaphor**: a real case, reworked so it can be
  played in public. Il carrello (stowaways in a landing gear, here a ground technician).
- **Human choices with a strong reason**: Il gabbiano, la mongolfiera, il faro.
- **Reinterpretations**: who someone is, where we are, what an object is, when it happens.
  Romeo e Giulietta, il salone, la lettera, il treno.
A riddle can belong to more than one family. Do not add two riddles with the same mechanism.

### What the pivot overturns
A wrong assumption of the player: that there is a culprit (baita), a place (il salone), a
person's role (il faro), an identity (la lettera), the time (il treno), that the scene is as it
was (il cubo), that it is real (la prima).

### Shape
A chain (la mongolfiera), branches that meet at the end (il restauro, il treno: the time and the
wife), or a single leap (il barista: short, few facts, fine as a quick riddle).

### Rules
1. The knowledge needed is common once said, even if few think of it. Good: carbon monoxide has
   no smell. Bad: il canarino e il silo (niche).
2. A sentence true to the letter suggests the wrong reading.
   Good: "Da quel giorno non si fida più di sua moglie" (treno: it sounds like betrayal).
3. A harmless hook leads to the pivot if the player asks about it.
   Good: "Una domenica di maggio del 1966" (treno).
4. A strong false lead is born from the text alone. Good: the betrayal (treno), a killer (baita).
5. Behind the leap there are more steps, so the questions do not end there.
6. The final key cannot be guessed from the text. Bad: il volo (the betrayal was obvious).
7. Credible, short to say aloud, translatable: no wordplay. Bad: il capello.
8. Not a double of a riddle in the collection. Bad: il balcone (la baita again).

## 2. Visible text, title, truth

1. The story holds only the scene and the anomaly: details and exclusions are facts to discover.
2. It ends with the question to answer, with nothing false in it.
   Good: "Cos'è successo?" Bad: "Chi l'ha ucciso?" (baita: nobody did).
3. The title and the visible figure reveal nothing.
   Bad: title "L'ora legale" (treno); a chimney on the house (baita).
4. Context and informative details (dates, history) go only in the truth, never in a fact the
   player must find. Good: "in Italia tornava l'ora legale dopo quasi vent'anni" (treno).
5. The truth is complete and in time order: the arbiter reads all of it, the conductor never.
   It names what the visible text leaves open, with the same words ("da quel giorno lui non si
   fida più di lei").

## 3. Facts

1. **Order of play**: the order in which a good host would lead the game, not the order in which
   things happened. The engine gives hints in this order.
   Bad: treno, first draft, with the mother's illness and the time change first because they
   happened first.
2. One statement per fact.
3. From vague to specific; a vague fact does not already contain the specific one.
   Good: "La moglie si è dimenticata di fare una cosa." then "Gli orologi di casa erano indietro."
   Bad: "La moglie si è dimenticata di spostare gli orologi." (it says what she forgot).
4. No step the player takes as already said. Bad: "Era già cieco anni prima." after "È cieco." (gabbiano).
5. No parallel steps that follow by themselves. Bad: "La madre è morta prima che arrivasse.",
   "Ha preso il treno successivo." (treno: obvious once the mother was dying).
6. A key fact (S, C and what presupposes them) is the minimal statement: the verifier wants
   every word of it in the question. Good: "C'era il cambio dell'ora."
   Bad: "Quella notte arrivava l'ora legale." (a player saying "cambio dell'ora" misses "quella
   notte"); "Sull'isola ha mangiato la carne di suo figlio" (gabbiano).
7. Every notable element of the visible text is named by a fact or by the truth.
   Bad: baita, "impronte" missing everywhere: the arbiter stopped linking the question.
8. `requires` means "presupposes" and nothing else: finding a fact lights everything it
   requires. Never use it to delay a fact until the end, or finding that fact gives away the
   whole chain. Bad: treno, first version, "C'era il cambio dell'ora." requiring "La moglie si è
   dimenticata di fare una cosa.": asking about the time change won the game in one question.
   The order of play is the order of the list.
9. Few facts are fine (about 10): never pad. A false lead that almost every player explores
   can become a negative fact. Good: "Nessuno l'ha ucciso." (baita). The negative fact then
   replaces the false lead: never write both, or after a "no" the matcher picks one at random.
   Bad: treno, "La moglie lo tradiva." beside "La moglie non lo tradiva.": "l'ha tradito?" lit
   only the red star, "lo tradiva?" both.

## 4. Roles

1. P: a step, can be given as a hint. S: a leap, protected. C: the last step, the final key,
   protected.
2. Protected never means blocked: a player who states the whole fact finds it, and a player who
   states the whole solution wins.
3. A fact presupposed by almost every other one cannot be S or C: it cannot be protected.
   Bad: gabbiano, "C'entra qualcosa del suo passato." as S.
4. A human "why" is not required, and it is not always the key. When there is one, it can be a
   side thread that gives the story its weight while the key is elsewhere (treno: the dying
   mother explains why the missed train matters; the key is the time change). A side thread is
   never the last step and never a victory element.

## 5. False leads

1. An exclusion does not reuse a key word of a true fact without telling them apart.
   Bad: baita, "avvelenato" in the food exclusion made "è morto avvelenato?" a no.
2. `ruled_out_by` points to a fact that really rules the lead out, otherwise `null`.
   Bad: "La sveglia non ha suonato." ruled out by "Gli orologi di casa erano indietro."
3. The obvious answer is ruled out by a fact or an exclusion.

## 6. Victory

1. 2-3 elements in reasoning order: each answers the "why" left open by the previous one.
2. Written with the player's words. Good: "il camino era bloccato". Bad: "comignolo".
3. `why` is what stays unexplained without the element, written after "perché", with no word of
   a hidden fact. Good: "il fumo è rimasto nella stanza, quella notte?" (baita).
4. At least one element depends on a leap or the final key. Side threads are not elements
   (treno: the mother).

## 7. Scenes and hints

1. A sealed scene's `hint` completes "Prova a pensare a ..." and points to a place or a time,
   not to the key. Good: "cosa è successo in casa prima che uscisse".
   Bad: "cosa è successo in casa, la notte prima" (it points at the time change).

## 8. Sky

1. `figure` shows the visible scene, `truth_figure` the truth; both are names in
   `static/figures.js`, reused when they fit. The atlas drawing is optional.
   The truth figure has no more main stars than the facts that are not optional: at the end
   every one of them is lit, and the figure must be complete (treno: 9 facts, 9 stars).
2. `name` is mythological or Latin; `epithet` alludes to the guilt or the lesson.
   Good: THANATOS, "Il fratello del sonno" (baita); CHRONOS, "L'ora perduta" (treno).

## Checked by the tests

- Ids unique; every `requires`, `ruled_out_by` and scene points to something that exists.
- `requires` has no cycles; every fact is reachable.
- Every scene has a fact; every sealed scene has a `hint`.
- Every victory element has `claim`, `why` and `requires`; at least one depends on S or C.
- The facts needed to win are fewer than all the facts.
- The story ends with "?".
- `figure` and `truth_figure` exist in `static/figures.js`.
- Every card is listed in `puzzles/index.json`.