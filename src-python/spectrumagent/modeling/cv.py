"""Cube groups never silently fall back to pixel-random cross validation."""
import numpy as np
from sklearn.model_selection import GroupKFold, KFold, StratifiedKFold

from . import ModelingError


def plan_folds(y, groups, *, task, strategy, folds, seed):
    y, groups = np.asarray(y), np.asarray(groups)
    if y.ndim != 1 or groups.shape != y.shape or not len(y) or type(folds) is not int or folds < 2:
        raise ModelingError("INVALID_CV_PARAMS", "CV 须为同长非空标签/组向量且折数至少2")
    if task not in ("classification", "regression") or strategy not in ("group_kfold", "random"):
        raise ModelingError("INVALID_CV_PARAMS", "未知任务或CV策略")
    count = len(np.unique(groups))
    if strategy == "group_kfold" and count < folds:
        raise ModelingError("INSUFFICIENT_GROUPS", f"实际组数 {count}，请求折数 {folds}；需多数据集或样品分组能力",
                            n_groups=count, requested_folds=folds)
    dummy = np.zeros(len(y))
    if strategy == "group_kfold":
        splitter = GroupKFold(n_splits=folds)
        splits = splitter.split(dummy, y, groups)
    else:
        splitter = (StratifiedKFold if task == "classification" else KFold)(n_splits=folds, shuffle=True, random_state=seed)
        splits = splitter.split(dummy, y)
    try:
        return [{"fold_index": i, "train_idx": train, "test_idx": test,
                 "train_groups": np.unique(groups[train]).tolist(), "test_groups": np.unique(groups[test]).tolist()}
                for i, (train, test) in enumerate(splits)]
    except ValueError as error:
        raise ModelingError("INVALID_CV_PARAMS", "样本或类别计数不足以划分请求的折数") from error
