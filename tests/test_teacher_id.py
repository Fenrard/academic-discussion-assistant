from evaluation.teacher_id import compute_confusion_counts, compute_teacher_id_metrics


def test_perfect_predictions():
    predictions = [True, True, False, False]
    actuals = [True, True, False, False]
    result = compute_teacher_id_metrics(predictions, actuals)

    assert result["accuracy"] == 1.0
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0
    assert result["false_accept_rate"] == 0.0
    assert result["false_reject_rate"] == 0.0


def test_false_accept_and_false_reject():
    # actuals: 3 enrolled (teacher) segments, 1 unenrolled. 1 unenrolled wrongly accepted (FP),
    # 1 of the 3 enrolled segments wrongly rejected (FN).
    predictions = [True, True, True, False]
    actuals =     [True, False, True, True]
    result = compute_teacher_id_metrics(predictions, actuals)

    counts = result["counts"]
    assert counts["true_positive"] == 2
    assert counts["false_positive"] == 1
    assert counts["false_negative"] == 1
    assert counts["true_negative"] == 0
    assert result["accuracy"] == round(2 / 4, 4)  # 2 correct (TP) out of 4 segments, TN==0
    assert result["false_accept_rate"] == 1.0  # only unenrolled segment, and it was accepted
    assert result["false_reject_rate"] == round(1 / 3, 4)  # 1 of 3 enrolled segments rejected


def test_mismatched_lengths_raises():
    try:
        compute_teacher_id_metrics([True], [True, False])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_empty_input_raises():
    try:
        compute_teacher_id_metrics([], [])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_confusion_counts_all_negative():
    counts = compute_confusion_counts([False, False], [False, False])
    assert counts.true_negative == 2
    assert counts.true_positive == counts.false_positive == counts.false_negative == 0
