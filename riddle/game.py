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
        """Return what the player sees: the cards not merged yet, and the ruled-out leads.

        A lit card disappears from the board once a lit deduction merges it, so
        the board grows while facts are found and shrinks while they are linked,
        down to the solution alone.

        Returns:
            A dict with "cards" (ids of the lit facts and deductions not merged
            into a lit deduction) and "ruled_out" (ids of the lit exclusions),
            both in the order they were lit.
        """
        merged = {child for d in self.puzzle.deductions if d["id"] in self.lit for child in d["children"]}
        exclusions = self.puzzle.exclusions
        return {
            "cards": [card for card in self.lit if card not in merged and card not in exclusions],
            "ruled_out": [card for card in self.lit if card in exclusions],
        }