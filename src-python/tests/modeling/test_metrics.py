import numpy as np
import pytest
from sklearn.metrics import cohen_kappa_score

from spectrumagent.data import DataError
from spectrumagent.modeling.metrics import score_predictions, summarize_folds


def test_classification_hand_calculation_votes_and_gap_record():
    report = {}
    result = score_predictions([0, 0, 1, 1], [0, 1, 1, 1], [0, 0, 1, 1], task="classification", leak_report=report)
    assert result["pixel"] == {"oa": .75, "kappa": .5, "confusion": [[1, 1], [0, 2]], "labels": [0, 1]}
    assert result["sample"] == {"oa": 1., "kappa": 1., "confusion": [[1, 0], [0, 1]], "labels": [0, 1]}
    assert report["pixel_sample_gap_warning"] == {"metric": "oa", "pixel": .75, "sample": 1., "gap": .25}
    print("METRIC_GAP pixel_oa=0.75 sample_oa=1.0 gap=0.25")


def test_kappa_is_unweighted_and_labels_include_predictions_in_sorted_order():
    true, predicted = [0, 0, 1, 1, 2, 2], [0, 2, 1, 2, 2, 0]
    result = score_predictions(true, predicted, range(6), task="classification")["pixel"]
    assert result["kappa"] == pytest.approx(cohen_kappa_score(true, predicted))
    assert result["kappa"] != pytest.approx(cohen_kappa_score(true, predicted, weights="quadratic"))
    assert result["labels"] == [0, 1, 2]


def test_regression_rmsep_and_r2_hand_calculation():
    result = score_predictions([0, 2, 4], [0, 1, 5], [0, 1, 2], task="regression")
    for scope in ("pixel", "sample"):
        assert result[scope]["rmse"] == result[scope]["rmsep"] == pytest.approx(np.sqrt(2/3))
        assert result[scope]["r2"] == pytest.approx(.75)


def test_unequal_classification_folds_pool_predictions_instead_of_fold_means():
    result = summarize_folds([{"y_true": [0], "y_pred": [0], "groups": [0]},
                              {"y_true": [1, 1, 1], "y_pred": [0, 0, 0], "groups": [1, 1, 1]}], task="classification")
    assert result["pixel"]["oa"] == .25 and result["pixel"]["oa"] != .5
    assert result["sample"]["oa"] == .5


def test_unequal_regression_folds_use_count_weighted_rmse_not_simple_or_pooled_rmse():
    result = summarize_folds([{"y_true": [0], "y_pred": [0], "groups": [0]},
                              {"y_true": [1, 2, 3], "y_pred": [3, 4, 5], "groups": [1, 2, 3]}], task="regression")
    for scope in ("pixel", "sample"):
        assert result[scope]["rmse"] == result[scope]["rmsep"] == 1.5
        assert result[scope]["rmse"] != 1 and result[scope]["rmse"] != pytest.approx(np.sqrt(3))
        assert result[scope]["r2"] == pytest.approx(-1.4)


@pytest.mark.parametrize("true,predicted,groups", [([], [], []), ([0], [0, 1], [0]), ([0], [np.nan], [0])])
def test_invalid_metric_vectors_refuse(true, predicted, groups):
    with pytest.raises(DataError):
        score_predictions(true, predicted, groups, task="classification")
