"""Game state for one play of a puzzle: lit cards, score and conversation."""


class Game:
    """One game of a puzzle.

    Cards confirmed by the judge are earned and scored. The cards they imply
    (prerequisites, and the two children of a deduction) are lit too, as
    explanation, but are worth no points.

    Attributes:
        puzzle: The `Puzzle` being played.
        lit: Ids of the lit cards, in the order they were lit.
        score: Points earned so far.
        history: (positive question, answer) pairs, used as context by the judge.
    """

    def __init__(self, puzzle):
        """Start a new game with no cards lit.

        Args:
            puzzle: The `Puzzle` to play.
        """
        self.puzzle = puzzle
        self.lit = []
        self.score = 0
        self.history = []

    def unlock(self, cards):
        """Light the confirmed cards and, in chain, the cards they imply.

        Args:
            cards: Ids of the cards confirmed by the judge.

        Returns:
            The ids of the newly lit cards, in the order they were lit.
        """
        before = len(self.lit)
        queue = [(card, True) for card in cards]   # (card, earned by the player)
        while queue:
            card, earned = queue.pop(0)
            if card in self.lit:
                continue
            self.lit.append(card)
            if earned:
                self.score += self.puzzle.points[card]
            queue.extend((implied, False) for implied in self.puzzle.implies.get(card, ()))
        return self.lit[before:]

    def won(self):
        """Return True once the root of the deduction tree, the solution, is lit."""
        return self.puzzle.root in self.lit

    def board(self):
        """Return what the player sees: cards, ruled-out leads, threads and guide questions.

        A lit card disappears once a lit deduction merges it, so the board grows
        while facts are found and shrinks while they are linked. A card that no
        deduction merges disappears once a lit card presupposes it (the other
        person, once we know it is the son).

        Returns:
            A dict with:
                "cards": ids of the lit facts and deductions still in view;
                "ruled_out": ids of the lit exclusions, hidden while their zone is sealed;
                "past_open": True once a card of the past is lit;
                "threads": the deductions the player can state now, each as
                    {"id", "zone", "theory", "cards", "question"}: "cards" are
                    the cards in view to link, "question" the guide, if any;
                "guides": the other guide questions, each as {"card", "zone", "question"},
                    in the zone of the last card they follow.
        """
        puzzle = self.puzzle
        lit = set(self.lit)

        def in_view(card):
            # the card itself, or the lit deduction that has merged it, in chain
            while puzzle.parent.get(card) in lit:
                card = puzzle.parent[card]
            return card

        # cards that some lit card presupposes: they hide if no deduction merges them
        presupposed = {c for card in lit for c in puzzle.prerequisites.get(card, ())}
        cards = [card for card in self.lit
                 if card not in puzzle.exclusions and in_view(card) == card
                 and not (card not in puzzle.parent and card in presupposed)]

        # the past opens with its first fact or deduction; its ruled-out leads wait until then
        past_open = any(puzzle.card_zone[card] == "past" for card in lit if card not in puzzle.exclusions)
        ruled_out = [card for card in self.lit if card in puzzle.exclusions
                     and (past_open or puzzle.card_zone[card] != "past")]

        # guide questions whose cards are all lit and whose target is not
        questions = {g["card"]: g["question"] for g in puzzle.guides
                     if set(g["after"]) <= lit and g["card"] not in lit}

        # a thread for every deduction reachable now; a guide on the same deduction goes on its thread
        threads = []
        for d in puzzle.deductions:
            if puzzle.is_reachable(d["id"], lit):
                threads.append({
                    "id": d["id"],
                    "zone": puzzle.card_zone[d["id"]],
                    "theory": d["id"] in puzzle.theories,
                    "cards": list(dict.fromkeys(in_view(c) for c in puzzle.needs[d["id"]])),   # no duplicates
                    "question": questions.pop(d["id"], None),
                })
        # a guide stands where the player is looking: next to the last card it follows, or where its target is;
        # while the past is sealed the player only sees the restaurant, so every guide stands there
        guides = [{"card": g["card"], "question": g["question"],
                   "zone": puzzle.card_zone[(g["after"] or [g["card"]])[-1]] if past_open else "restaurant"}
                  for g in puzzle.guides if g["card"] in questions]

        return {"cards": cards, "ruled_out": ruled_out, "past_open": past_open,
                "threads": threads, "guides": guides}