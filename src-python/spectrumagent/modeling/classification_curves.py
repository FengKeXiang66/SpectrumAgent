"""OOF ranking and rejection diagnostics; never transmit per-pixel scores."""
import numpy as np
from .evaluation import Evaluations
from .metrics import _vote
from . import ModelingError


def sampled_points(x, y, maximum=2048):
    index = np.unique(np.linspace(0, len(x)-1, min(maximum, len(x)), dtype=int))
    return [{"x": float(x[i]), "y": float(y[i])} for i in index if np.isfinite(x[i]) and np.isfinite(y[i])]


def binary_curve(truth, scores):
    from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve

    truth = np.asarray(truth, dtype=bool)
    positive, negative = int(truth.sum()), int((~truth).sum())
    result = {"positive": positive, "negative": negative, "roc_auc": None, "ap": None,
              "roc": [], "pr": [], "undefined_reason": None, "positive_fraction": float(truth.mean()) if len(truth) else None}
    if not positive:
        result["undefined_reason"] = "no_positive_support"
        return result
    precision, recall, _ = precision_recall_curve(truth, scores)
    result.update(pr=sampled_points(recall[::-1], precision[::-1]), ap=float(average_precision_score(truth, scores)))
    if not negative:
        result["undefined_reason"] = "no_negative_support_for_ROC"
        return result
    fpr, tpr, _ = roc_curve(truth, scores, drop_intermediate=False)
    result.update(roc_auc=float(roc_auc_score(truth, scores)), roc=sampled_points(fpr, tpr),
                  original_roc_points=len(fpr), original_pr_points=len(precision))
    return result


def curves(store: Evaluations, identifier, *, scope="pixel", offset=0, limit=5):
    from sklearn.metrics import roc_curve

    if scope not in ("pixel", "sample") or offset < 0 or not 1 <= limit <= 5:
        raise ModelingError("INVALID_CURVE_REQUEST", "曲线范围非法")
    kind = "curves-" + scope + "-" + str(offset) + "-" + str(limit)
    try:
        return store.artifact(identifier, kind)
    except ModelingError as error:
        if error.code != "ARTIFACT_NOT_FOUND":
            raise
    ev = store.get(identifier)
    obs = store.artifact(identifier, "observations", fields=["y", "groups", "probabilities"])
    if "probabilities" not in obs:
        raise ModelingError("RANKING_SCORES_UNAVAILABLE", "当前推理评价只保存最大得分，不能重建逐类ROC/PR")
    true, probability = obs["y"], obs["probabilities"]
    confidence, prediction = probability.max(axis=1), probability.argmax(axis=1)
    if scope == "sample":
        gs = np.unique(obs["groups"])
        true = np.asarray([_vote(true[obs["groups"] == g]) for g in gs])
        probability = np.stack([probability[obs["groups"] == g].mean(axis=0) for g in gs])
    labels = np.arange(probability.shape[1])
    all_curves = [binary_curve(true == label, probability[:, label]) for label in labels]
    selected = [{"label": int(i), "name": ev["classes"][i]["name"], **all_curves[i]}
                for i in labels[offset:offset+limit]]
    def mean(name):
        values = [r[name] for r in all_curves if r[name] is not None]
        return float(np.mean(values)) if values else None
    grid = np.linspace(0, 1, 1001)
    interpolated = []
    for label, row in zip(labels, all_curves):
        if row["roc_auc"] is not None:
            x, y, _ = roc_curve(true == label, probability[:, label], drop_intermediate=False)
            interpolated.append(np.interp(grid, x, y))
    risk = []
    thresholds = np.unique(np.r_[0., np.quantile(confidence, np.linspace(0, 1, min(510, len(confidence)))), 1.])
    for threshold in thresholds:
        accepted = confidence >= threshold
        n = int(accepted.sum())
        risk.append({"threshold": float(threshold), "coverage": n/len(confidence),
                     "risk": float(np.mean(prediction[accepted] != obs["y"][accepted])) if n else None,
                     "accepted": n, "rejected": len(confidence)-n})
    correct = prediction == obs["y"]
    bins = np.linspace(0, 1, 21)
    for cls in selected:
        cls["metric_refs"] = {name: store.scalar(identifier, {"name": name, "scope": scope, "population": "all_labeled",
                                                "class_id": cls["label"], "aggregation": "ovr"}, cls[name],
                                                cls["positive"]+cls["negative"], cls["undefined_reason"])
                              for name in ("roc_auc", "ap")}
    result = {"evaluation_id": identifier, "scope": scope, "population": "all_labeled",
              "score_definition": "uncalibrated_softmax", "aggregation": "mean_score" if scope == "sample" else "pixel",
              "offset": offset, "limit": limit, "total_classes": len(labels), "classes": selected,
              "macro_roc_auc": mean("roc_auc"), "macro_ap": mean("ap"),
              "valid_roc_classes": sum(r["roc_auc"] is not None for r in all_curves),
              "valid_ap_classes": sum(r["ap"] is not None for r in all_curves),
              "micro": binary_curve((true[:, None] == labels).ravel(), probability.ravel()),
              "macro_roc": sampled_points(grid, np.mean(interpolated, axis=0)) if interpolated else [],
              "risk_coverage_scope": "pixel", "risk_coverage": risk,
              "histogram": {"edges": bins.tolist(), "correct": np.histogram(confidence[correct], bins)[0].tolist(),
                            "incorrect": np.histogram(confidence[~correct], bins)[0].tolist()},
              "source": ev["artifacts"]["observations"],
              "limitation": "AP不是梯形PR-AUC；样品曲线按均值得分聚合，不是多数投票决策；分数未校准。"}
    from .evaluation import encode
    if len(encode(result).encode("utf-8")) > 1024*1024:
        raise ModelingError("RESPONSE_TOO_LARGE", "请减少曲线类别数")
    result["metric_refs"] = {name: store.scalar(identifier, {"name": name, "scope": scope, "population": "all_labeled",
                                                          "aggregation": "macro"}, result[name],
                                                          result["valid_roc_classes" if name == "macro_roc_auc" else "valid_ap_classes"],
                                                          "no_defined_classes" if result[name] is None else None)
                            for name in ("macro_roc_auc", "macro_ap")}
    result["micro"]["metric_refs"] = {name: store.scalar(identifier, {"name": name, "scope": scope,
        "population": "all_labeled", "aggregation": "micro"}, result["micro"][name], result["micro"]["positive"]+result["micro"]["negative"],
        result["micro"]["undefined_reason"])
        for name in ("roc_auc", "ap")}
    store.cache(identifier, kind, result)
    return result
