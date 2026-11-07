"""Pure metrics, never database writes.

Classification summaries pool all held-out predictions, not fold means.
Regression summary RMSE/RMSEP is the sample-count-weighted fold RMSE;
summary R2 is recalculated on pooled predictions. Sample scope follows R5
majority voting per cube; ties use the smallest sorted value deterministically.
Undefined sklearn scores are represented by None, never fabricated as zero.
"""
import numpy as np
from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix, mean_squared_error, r2_score

from . import ModelingError

REGRESSION_METRICS = {"rmse": "RMSEC", "r2": "R²C", "rmsep": "RMSEP", "r2p": "R²P",
                      "rpd": "RPD", "rer": "RER", "bias": "偏差"}


def _vectors(y_true, y_pred, groups):
    true, predicted, groups = np.asarray(y_true), np.asarray(y_pred), np.asarray(groups)
    if true.ndim != 1 or predicted.shape != true.shape or groups.shape != true.shape or not len(true):
        raise ModelingError("INVALID_METRIC_INPUT", "指标需要同长非空预测/真值/组向量")
    if not np.isfinite(true).all() or not np.isfinite(predicted).all():
        raise ModelingError("INVALID_METRIC_INPUT", "指标输入必须有限")
    return true, predicted, groups


def _vote(values):
    values, counts = np.unique(values, return_counts=True)
    return values[np.argmax(counts)]


def _sample(true, predicted, groups):
    keys = np.unique(groups)
    return (np.asarray([_vote(true[groups == group]) for group in keys]),
            np.asarray([_vote(predicted[groups == group]) for group in keys]))


def _finite(value):
    return float(value) if np.isfinite(value) else None


def _score(true, predicted, task):
    if task == "classification":
        labels = np.unique(np.concatenate([true, predicted]))
        return {"oa": float(accuracy_score(true, predicted)), "kappa": _finite(cohen_kappa_score(true, predicted, weights=None)),
                "confusion": confusion_matrix(true, predicted, labels=labels).tolist(), "labels": labels.tolist()}
    if task == "regression":
        rmse = float(np.sqrt(mean_squared_error(true, predicted)))
        return {"rmse": rmse, "rmsep": rmse, "r2": _finite(r2_score(true, predicted))}
    raise ModelingError("INVALID_METRIC_INPUT", "未知指标任务")


def _gap(scores, task, leak_report):
    if "pixel" not in scores:
        return
    if leak_report is not None:
        name = "oa" if task == "classification" else "rmse"
        pixel, sample = scores["pixel"][name], scores["sample"][name]
        gap = abs(pixel-sample)
        if gap > .1:
            leak_report["pixel_sample_gap_warning"] = {"metric": name, "pixel": pixel, "sample": sample, "gap": gap}
        else:
            leak_report.pop("pixel_sample_gap_warning", None)


def score_predictions(y_true, y_pred, groups, *, task, leak_report=None):
    true, predicted, groups = _vectors(y_true, y_pred, groups)
    sample_true, sample_predicted = _sample(true, predicted, groups)
    scores = {"pixel": _score(true, predicted, task), "sample": _score(sample_true, sample_predicted, task)}
    _gap(scores, task, leak_report)
    return scores


def summarize_folds(predictions, *, task, leak_report=None):
    """fold_index=NULL: pooled classification; count-weighted regression RMSE.

    Counts mean pixels for pixel scope and cube votes for sample scope.
    R2 uses pooled predictions; do not average per-fold R2 or weight by folds.
    """
    if not predictions:
        raise ModelingError("INVALID_METRIC_INPUT", "汇总至少需要一折预测")
    vectors = [_vectors(row["y_true"], row["y_pred"], row["groups"]) for row in predictions]
    pooled = [np.concatenate([item[i] for item in vectors]) for i in range(3)]
    result = score_predictions(*pooled, task=task)
    if task == "regression":
        for scope in ("pixel", "sample"):
            scores, weights = [], []
            for true, predicted, groups in vectors:
                if scope == "sample":
                    true, predicted = _sample(true, predicted, groups)
                scores.append(float(np.sqrt(mean_squared_error(true, predicted))))
                weights.append(len(true))
            result[scope]["rmse"] = result[scope]["rmsep"] = float(np.average(scores, weights=weights))
    _gap(result, task, leak_report)
    return result


def _regression(true, predicted, set):
    true, predicted = np.asarray(true, dtype=float), np.asarray(predicted, dtype=float)
    if true.ndim != 1 or predicted.shape != true.shape or not len(true) or not np.isfinite(true).all() or not np.isfinite(predicted).all():
        raise ModelingError("INVALID_METRIC_INPUT", "回归指标需要同长非空有限向量")
    rmse = float(np.sqrt(np.mean((predicted-true)**2)))
    r2 = float(r2_score(true, predicted)) if len(true) > 1 and np.ptp(true) > 0 else None
    if set == "calibration":
        return {"rmse": rmse, "r2": r2}
    if set != "prediction":
        raise ModelingError("INVALID_METRIC_INPUT", "未知校准/预测集合")
    return {"rmsep": rmse, "r2p": r2,
            "rpd": float(np.std(true, ddof=1)/rmse) if len(true) > 1 and np.ptp(true) > 0 and rmse > 0 else None,
            "rer": float(np.ptp(true)/rmse) if len(true) > 1 and np.ptp(true) > 0 and rmse > 0 else None,
            "bias": float(np.mean(predicted-true))}


def derive_classification(score):
    """R10: undefined denominators remain None; no epsilon or zero imputation."""
    matrix = np.asarray(score["confusion"], dtype=np.int64)
    classes = []
    for i, label in enumerate(score["labels"]):
        support, predicted = int(matrix[i].sum()), int(matrix[:, i].sum())
        recall = float(matrix[i, i]/support) if support else None
        precision = float(matrix[i, i]/predicted) if predicted else None
        f1 = (2*precision*recall/(precision+recall)
              if precision is not None and recall is not None and precision+recall > 0 else None)
        classes.append({"label": label, "precision": precision, "recall": recall, "f1": f1})
    def average(key):
        values = [item[key] for item in classes if item[key] is not None]
        return float(np.mean(values)) if values else None
    return {**score, "aa": average("recall"), "macro_f1": average("f1"), "per_class": classes}


def classification_scores(y_true, y_pred, groups, *, labels):
    """Reuse pixel/sample majority votes after removing explicitly rejected pixels."""
    true, predicted, groups = _vectors(y_true, y_pred, groups)
    accepted = (true >= 0) & (predicted >= 0)
    scores = score_predictions(true[accepted], predicted[accepted], groups[accepted], task="classification") if accepted.any() else None
    result = {}
    for scope in ("pixel", "sample"):
        matrix = np.zeros((len(labels), len(labels)), dtype=np.int64)
        score = scores[scope] if scores else {"oa": None, "kappa": None, "labels": [], "confusion": []}
        index = {label: i for i, label in enumerate(labels)}
        for i, left in enumerate(score["labels"]):
            for j, right in enumerate(score["labels"]):
                matrix[index[left], index[right]] = score["confusion"][i][j]
        result[scope] = derive_classification({**score, "labels": list(labels), "confusion": matrix.tolist()})
    return result


def classification_fold_summary(folds):
    """Fold statistics use defined scores only; SD needs two defined folds."""
    def summary(values):
        finite = [value for value in values if value is not None]
        return {"mean": float(np.mean(finite)) if finite else None,
                "std": float(np.std(finite, ddof=1)) if len(finite) > 1 else None}
    return {scope: {
        **{name: summary([fold[scope][name] for fold in folds]) for name in ("oa", "kappa", "aa", "macro_f1")},
        "per_class": [{"label": item["label"], **{
            name: summary([fold[scope]["per_class"][i][name] for fold in folds])
            for name in ("precision", "recall", "f1")}}
            for i, item in enumerate(folds[0][scope]["per_class"])]}
        for scope in ("pixel", "sample")}
