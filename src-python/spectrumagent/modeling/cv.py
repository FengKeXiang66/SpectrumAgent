"""Cube groups never silently fall back to pixel-random cross validation."""
import numpy as np
from sklearn.model_selection import GroupKFold, KFold, StratifiedKFold, LeaveOneOut

from . import ModelingError


def plan_folds(y, groups, *, task, strategy, folds, seed):
    y, groups = np.asarray(y), np.asarray(groups)
    if y.ndim != 1 or groups.shape != y.shape or not len(y) or type(folds) is not int or folds < 2:
        raise ModelingError("INVALID_CV_PARAMS", "CV 须为同长非空标签/组向量且折数至少2")
    if task not in ("classification", "regression") or strategy not in ("group_kfold", "random", "kfold", "loo"):
        raise ModelingError("INVALID_CV_PARAMS", "未知任务或CV策略")
    if task == "regression" and strategy not in ("kfold", "loo"):
        raise ModelingError("INVALID_CV_PARAMS", "整样谱回归仅支持 KFold/LOO，分组键仍由平台推导")
    count = len(np.unique(groups))
    if strategy == "group_kfold" and count < folds:
        raise ModelingError("INSUFFICIENT_GROUPS", f"实际组数 {count}，请求折数 {folds}；需多数据集或样品分组能力",
                            n_groups=count, requested_folds=folds)
    dummy = np.zeros(len(y))
    if strategy == "group_kfold":
        splitter = GroupKFold(n_splits=folds)
        splits = splitter.split(dummy, y, groups)
    elif strategy == "loo":
        if folds != len(y):
            raise ModelingError("INVALID_CV_PARAMS", "LOO 折数须等于训练样本数")
        splits = LeaveOneOut().split(dummy)
    elif strategy == "kfold":
        splits = KFold(n_splits=folds, shuffle=True, random_state=seed).split(dummy)
    else:
        splitter = (StratifiedKFold if task == "classification" else KFold)(n_splits=folds, shuffle=True, random_state=seed)
        splits = splitter.split(dummy, y)
    try:
        return [{"fold_index": i, "train_idx": train, "test_idx": test,
                 "train_groups": np.unique(groups[train]).tolist(), "test_groups": np.unique(groups[test]).tolist()}
                for i, (train, test) in enumerate(splits)]
    except ValueError as error:
        raise ModelingError("INVALID_CV_PARAMS", "样本或类别计数不足以划分请求的折数") from error


def kennard_stone(X, y, cube_ids, *, test_ratio=1/3):
    """Deterministic z-score Euclidean max-min; ties use cube_id, never a seed."""
    X, y = np.asarray(X, dtype=float), np.asarray(y, dtype=float)
    n = len(y)
    if X.ndim != 2 or X.shape[0] != n or len(cube_ids) != n or len(set(cube_ids)) != n or n < 4 or not 0 < test_ratio < 1:
        raise ModelingError("INVALID_SPLIT", "KS 需要至少4个独立样品及合法测试比例")
    if not np.isfinite(X).all() or not np.isfinite(y).all():
        raise ModelingError("INVALID_SPLIT", "KS 输入须为有限数值")
    order = np.asarray(sorted(range(n), key=lambda i: cube_ids[i]))
    values = X[order]
    std = values.std(axis=0)
    z = (values-values.mean(axis=0))/np.where(std > 0, std, 1)
    distances = np.sqrt(((z[:, None]-z[None, :])**2).sum(axis=2))
    n_train = round(n*(1-test_ratio))
    if not 2 <= n_train < n:
        raise ModelingError("INVALID_SPLIT", "划分后须至少2个训练样品及1个测试样品")
    farthest = np.where(np.triu(np.ones((n, n), dtype=bool), 1), distances, -np.inf)
    pair = np.unravel_index(np.argmax(farthest), farthest.shape)
    def extend(seeds):
        train = sorted(set(seeds))
        if len(train) > n_train:
            raise ModelingError("COVERAGE_UNREPAIRED", "训练容量不足以纳入 KS 初始对和含量极值")
        while len(train) < n_train:
            pool = [i for i in range(n) if i not in train]
            train.append(pool[int(np.argmax(distances[np.ix_(pool, train)].min(axis=1)))])
        return sorted(train)
    train = extend(pair)
    sorted_y = y[order]
    def covered(train):
        test = [i for i in range(n) if i not in train]
        return bool(np.all((sorted_y[test] >= sorted_y[train].min()) & (sorted_y[test] <= sorted_y[train].max())))
    repaired = not covered(train)
    if repaired:
        train = extend([*pair, int(np.argmin(sorted_y)), int(np.argmax(sorted_y))])
        if not covered(train):
            raise ModelingError("COVERAGE_UNREPAIRED", "含量范围修复后仍未覆盖测试集")
    test = [i for i in range(n) if i not in train]
    return {"train_idx": order[train], "test_idx": order[test], "coverage_repaired": repaired}
