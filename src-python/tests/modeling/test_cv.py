import numpy as np
import pytest
from sklearn.model_selection import KFold, StratifiedKFold

from spectrumagent.data import DataError
from spectrumagent.modeling.run import TrainingRuns
from spectrumagent.modeling.cv import plan_folds


def test_four_cubes_are_exactly_four_non_overlapping_groups():
    groups = np.repeat(np.arange(4), 6)
    y = np.tile([0, 1], 12)
    folds = plan_folds(y, groups, task="classification", strategy="group_kfold", folds=2, seed=17)
    for fold in folds:
        assert len(fold["train_groups"]) == len(fold["test_groups"]) == 2
        assert not set(fold["train_groups"]) & set(fold["test_groups"])
        assert len(fold["train_idx"]) == len(fold["test_idx"]) == 12
    np.testing.assert_array_equal(np.sort(np.concatenate([f["test_idx"] for f in folds])), np.arange(24))


def test_single_cube_refuses_group_cv_with_actual_counts():
    with pytest.raises(DataError) as error:
        plan_folds([0, 1, 0, 1], [0]*4, task="classification", strategy="group_kfold", folds=2, seed=17)
    assert error.value.code == "INSUFFICIENT_GROUPS"
    assert "1" in str(error.value) and "2" in str(error.value) and "需多数据集或样品分组能力" in str(error.value)


@pytest.mark.parametrize("task,strategy", [("classification", "group_kfold"), ("classification", "random"), ("regression", "kfold")])
def test_seed_reproducible_and_random_uses_required_splitter(task, strategy):
    y = np.tile([0, 1], 12)
    groups = np.repeat(np.arange(4), 6)
    kwargs = dict(task=task, strategy=strategy, folds=2, seed=17)
    a, b = plan_folds(y, groups, **kwargs), plan_folds(y, groups, **kwargs)
    for first, second in zip(a, b):
        for key in ("train_idx", "test_idx"):
            np.testing.assert_array_equal(first[key], second[key])
    if strategy == "random":
        cls = StratifiedKFold if task == "classification" else KFold
        expected = list(cls(2, shuffle=True, random_state=17).split(np.zeros(len(y)), y))
        for fold, (_, test) in zip(a, expected):
            np.testing.assert_array_equal(fold["test_idx"], test)
            if task == "classification":
                assert np.bincount(y[test]).tolist() == [6, 6]


@pytest.mark.parametrize("y,groups,folds", [([], [], 2), ([0], [0, 1], 2), ([0, 1], [0, 1], 1)])
def test_invalid_cv_vectors_rejected(y, groups, folds):
    with pytest.raises(DataError, match="CV"):
        plan_folds(y, groups, task="classification", strategy="group_kfold", folds=folds, seed=17)


def test_preflight_random_allows_five_folds_with_four_cube_groups(model_case):
    c = model_case
    result = TrainingRuns(c.registry, c.paths).preflight(**c.arguments, task="classification",
             cv_strategy="random", cv_folds=5, seed=17)
    assert len(result["folds"]) == 5 and result["n_samples"] == 96
    assert result["leak_report"]["random_split_requested"] is True


@pytest.mark.parametrize("strategy", ["group_kfold", "random"])
def test_preflight_single_cube_refuses_any_strategy(model_case, strategy):
    c = model_case
    arguments = {key: value[:1] if isinstance(value, list) else value for key, value in c.arguments.items()}
    with pytest.raises(DataError) as error:
        TrainingRuns(c.registry, c.paths).preflight(**arguments, task="classification",
                     cv_strategy=strategy, cv_folds=5, seed=17)
    assert error.value.code == "INSUFFICIENT_GROUPS"
    assert "单数据集无法分组交叉验证" in str(error.value)


def test_preflight_group_folds_report_actual_and_requested_counts(model_case):
    c = model_case
    with pytest.raises(DataError) as error:
        TrainingRuns(c.registry, c.paths).preflight(**c.arguments, task="classification",
                     cv_strategy="group_kfold", cv_folds=5, seed=17)
    assert error.value.code == "INSUFFICIENT_GROUPS"
    assert "实际组数 4" in str(error.value) and "请求折数 5" in str(error.value)
