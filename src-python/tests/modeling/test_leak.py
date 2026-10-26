from copy import deepcopy

import numpy as np
import pytest

from spectrumagent.modeling.cv import plan_folds
from spectrumagent.modeling.leak import FULL_FIT_REASON, preflight_report


def inputs():
    meta = {"cubes": [{"cube_id": str(i), "input_fingerprint": f"fingerprint-{i}",
                       "source_hashes": {"header": "shared-header", "data": str(i)},
                       "pipeline": {"steps": [{"op": "standardize"}]}} for i in range(4)]}
    groups = np.repeat(np.arange(4), 6)
    folds = plan_folds(np.tile([0, 1], 12), groups, task="classification", strategy="group_kfold", folds=2, seed=17)
    return meta, folds


def test_three_preflight_findings_and_full_fit_acknowledgment_always_visible():
    meta, folds = inputs()
    report = preflight_report(meta, folds, strategy="group_kfold")
    assert report["passed"] and report["group_cross_fold"]["violation_count"] == 0
    assert report["duplicate_content"]["duplicate_count"] == 0
    assert report["preprocess_full_fit"] == {"acknowledged": True, "reason": FULL_FIT_REASON, "affected_steps": ["standardize"]}


@pytest.mark.parametrize("kind", ["input_fingerprint", "source_hashes"])
def test_duplicate_fingerprint_or_complete_source_content_is_reported(kind):
    meta, folds = inputs()
    meta["cubes"][1][kind] = deepcopy(meta["cubes"][0][kind])
    report = preflight_report(meta, folds, strategy="group_kfold")
    assert not report["passed"] and report["duplicate_content"]["duplicate_count"] == 1
    assert kind in report["duplicate_content"]["pairs"][0]["reasons"]


def test_overlap_is_failure_even_when_random_was_explicitly_requested():
    meta, folds = inputs()
    folds[0]["test_groups"].append(folds[0]["train_groups"][0])
    report = preflight_report(meta, folds, strategy="random")
    assert not report["passed"] and report["group_cross_fold"]["violation_count"] == 1
    assert report["random_split_requested"] is True and "随机" in report["random_split_warning"]
