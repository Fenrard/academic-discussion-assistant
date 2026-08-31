from evaluation.sus import aggregate_sus_scores, adjective_rating, compute_sus_score


def test_compute_sus_score_all_best_answers():
    # Odd items (positive): 5 is best -> score 4 each. Even items (negative): 1 is best -> score 4 each.
    responses = [5, 1, 5, 1, 5, 1, 5, 1, 5, 1]
    assert compute_sus_score(responses) == 100.0


def test_compute_sus_score_all_worst_answers():
    responses = [1, 5, 1, 5, 1, 5, 1, 5, 1, 5]
    assert compute_sus_score(responses) == 0.0


def test_compute_sus_score_neutral_answers():
    responses = [3] * 10
    assert compute_sus_score(responses) == 50.0


def test_compute_sus_score_wrong_length_raises():
    try:
        compute_sus_score([3] * 9)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_compute_sus_score_out_of_range_raises():
    try:
        compute_sus_score([3, 3, 3, 3, 3, 3, 3, 3, 3, 6])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_adjective_rating_bands():
    assert adjective_rating(90) == "Best Imaginable"
    assert adjective_rating(80) == "Excellent"
    assert adjective_rating(60) == "Good"
    assert adjective_rating(45) == "OK"
    assert adjective_rating(30) == "Poor"
    assert adjective_rating(10) == "Worst Imaginable"


def test_aggregate_sus_scores():
    respondents = [[5, 1, 5, 1, 5, 1, 5, 1, 5, 1], [1, 5, 1, 5, 1, 5, 1, 5, 1, 5]]
    result = aggregate_sus_scores(respondents)

    assert result["respondent_count"] == 2
    assert result["individual_scores"] == [100.0, 0.0]
    assert result["mean_score"] == 50.0
