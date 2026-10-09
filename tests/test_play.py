from riddle.play import offer_answer


def test_a_short_yes_or_no_answers_the_offer_and_a_question_does_not():
    assert [offer_answer(text) for text in ("Sì", "sì dai", "Ok grazie", "perché no")] == [True] * 4
    assert [offer_answer(text) for text in ("No", "no grazie", "meglio di no")] == [False] * 3
    assert offer_answer("Si è ucciso per il sapore della carne?") is None