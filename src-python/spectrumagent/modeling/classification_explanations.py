"""Frozen model coefficients, held-out permutation importance, audited comparisons."""
import numpy as np
from backend.database import connect_database
from .evaluation import encode, digest, NAMES
from .classification import predict
from .inference import apply_with_calibration
from .metrics import classification_scores
from . import ModelingError


def coefficients(store, identifier):
    ev, pack = store.get(identifier), store.artifact(identifier, "model")
    axis = pack["feature_axis"]
    features = [{"feature_id": "feature-" + str(i), "column": i+1,
                 "wavelength": axis[i] if axis is not None else None,
                 "unit": pack["wavelength_unit"] if axis is not None else None}
                for i in pack["columns"]]
    return {"evaluation_id": identifier, "classes": ev["classes"], "features": features,
            "coefficients": pack["model"]["coef"], "selected_lv": pack["model"]["selected_lv"],
            "source": ev["artifacts"]["model"], "scale": "PLS coefficient on frozen preprocessed feature scale; centered X",
            "limitation": "有符号线性系数，不是重要性排序；无可追溯波长轴时仅按特征/成分解释。"}


def importance(store, identifier, repeats=5, checkpoint=lambda phase: None):
    checkpoint("importance")
    if not 2 <= repeats <= 20:
        raise ModelingError("INVALID_IMPORTANCE_REQUEST", "重复次数须为2至20")
    kind = "importance-" + str(repeats)
    try:
        return store.artifact(identifier, kind)
    except ModelingError as error:
        if error.code != "ARTIFACT_NOT_FOUND":
            raise
    ev = store.get(identifier)
    if ev["protocol"] != "nested_group_cv":
        raise ModelingError("INDEPENDENT_EVALUATION_REQUIRED", "留出重要性需要严格外层评价")
    obs, folds = store.artifact(identifier, "observations", fields=["y", "groups", "fold_index"]), store.artifact(identifier, "fold_models")
    mixed = any(s["op"] in ("pca", "mnf", "ica") for s in folds[0]["calibration"]["pipeline"]["steps"])
    labels = list(range(len(ev["classes"])))
    aggregate, local = {}, []
    for pack in folds:
        checkpoint("importance:fold-"+str(pack["fold_index"]+1))
        mask = obs["fold_index"] == pack["fold_index"]
        y, groups = obs["y"][mask], obs["groups"][mask]
        transformed = apply_with_calibration(pack["calibration"], pack["calibration"]["pipeline"], store.spectra(identifier, mask))
        features = transformed[:, pack["columns"]]
        original = classification_scores(y, predict(features, pack["model"]).argmax(axis=1), groups, labels=labels)["pixel"]["macro_f1"]
        if original is None:
            continue
        fold_rows = []
        for j in range(transformed.shape[1]):
            checkpoint("importance:fold-"+str(pack["fold_index"]+1)+":feature-"+str(j+1))
            drops = []
            used = j in pack["columns"]
            for repeat in range(repeats):
                if used:
                    index = pack["columns"].index(j)
                    changed = features.copy()
                    rng = np.random.default_rng(ev["seed"] + pack["fold_index"]*1000003 + j*101 + repeat)
                    changed[:, index] = changed[rng.permutation(len(changed)), index]
                    score = classification_scores(y, predict(changed, pack["model"]).argmax(axis=1), groups, labels=labels)["pixel"]["macro_f1"]
                    drops.append(float(original-score) if score is not None else None)
                else:
                    drops.append(0.)
            defined = [d for d in drops if d is not None]
            item = {"feature_id": "feature-" + str(j), "column": j+1,
                    "wavelength": pack["feature_axis"][j] if pack["feature_axis"] is not None else None,
                    "unit": ev["wavelength_unit"] if pack["feature_axis"] is not None else None,
                    "drops": drops, "mean": float(np.mean(defined)) if defined else None,
                    "std": float(np.std(defined, ddof=1)) if len(defined) > 1 else None, "used": used}
            fold_rows.append(item)
            aggregate.setdefault(j, []).append(item)
        local.append({"fold_index": pack["fold_index"], "features": fold_rows})
    rows = []
    checkpoint("importance:aggregate")
    if not mixed:
        for j, items in aggregate.items():
            values = [r["mean"] for r in items if r["mean"] is not None]
            row = {k: items[0][k] for k in ("feature_id", "column", "wavelength", "unit")}
            row.update(mean=float(np.mean(values)) if values else None,
                       std=float(np.std(values, ddof=1)) if len(values) > 1 else None,
                       effective_folds=len(values), selection_frequency=sum(r["used"] for r in items)/len(folds))
            row["metric_id"] = store.scalar(identifier, {"name": "permutation_macro_f1_drop", "feature_id": row["feature_id"],
                                             "aggregation": "fold_mean", "repeats": repeats}, row["mean"], len(values))
            rows.append(row)
        rows.sort(key=lambda r: (r["mean"] is None, -(r["mean"] or 0), r["column"]))
    result = {"evaluation_id": identifier, "method": "held_out_repeated_permutation", "score": "all_labeled_pixel_macro_f1",
              "repeats": repeats, "seed": ev["seed"], "features": rows, "top5": rows[:5], "folds": local,
              "status": "per_fold_only" if mixed else "ready",
              "source": ev["artifacts"]["fold_models"],
              "limitation": "相关特征可掩盖或分摊重要性；置换改变联合分布；负值保留；成分轴不跨折冒充同一波长；不是化学因果证据。"}
    store.cache(identifier, kind, result)
    return result


def compare(store, left_id, right_id):
    left, right = store.get(left_id), store.get(right_id)
    checks = {}
    for key in ("protocol", "definition", "threshold", "group_kind"):
        checks[key] = left[key] == right[key]
    checks["classes"] = [c["id"] for c in left["classes"]] == [c["id"] for c in right["classes"]]
    for key in ("truth_hash", "position_hash", "fold_index_hash", "group_hash"):
        checks[key] = key in left["input_identity"] and key in right["input_identity"] and left["input_identity"][key] == right["input_identity"][key]
    checks["source_content"] = [c["source_hashes"] for c in left["cubes"]] == [c["source_hashes"] for c in right["cubes"]]
    def truth_identity(ev):
        return [(c["cube_id"], c["annotation_version_id"], c["snapshot_hash"], c["label_index_hash"]) for c in ev["cubes"]]
    checks["truth_objects"] = truth_identity(left) == truth_identity(right)
    differences = [key for key, valid in checks.items() if not valid]
    rows, per_class, folds, paired = [], [], [], []
    if not differences:
        for population in ("all_labeled", "accepted"):
            for scope in ("pixel", "sample"):
                def delta(name, a, b, *, class_id=None, fold_id=None):
                    identity = {"population": population, "scope": scope, "name": name, "class_id": class_id,
                                "fold_id": fold_id, "aggregation": "fold" if fold_id is not None else "pooled"}
                    left_ref = left["populations"][population]["scores"][scope]["metric_refs"].get(encode(identity))
                    right_ref = right["populations"][population]["scores"][scope]["metric_refs"].get(encode(identity))
                    difference = float(a-b) if a is not None and b is not None else None
                    key = {"name": "difference_"+name, "comparison_id": right_id, "scope": scope,
                           "population": population, "aggregation": identity["aggregation"]}
                    if class_id is not None:
                        key["class_id"] = class_id
                    if fold_id is not None:
                        key["fold_id"] = fold_id
                    mid = store.scalar(left_id, key, difference, reason="one_or_both_undefined" if difference is None else None)
                    return {"population": population, "scope": scope, "name": name, "left": a, "right": b,
                            "difference": difference, "metric_id": mid, "left_metric_id": left_ref, "right_metric_id": right_ref,
                            "unit": "percentage_points" if name in ("oa", "aa", "coverage", "recall", "precision") else "absolute"}
                for name in (*NAMES, "coverage"):
                    a = left["populations"][population]["scores"][scope][name]
                    b = right["populations"][population]["scores"][scope][name]
                    rows.append(delta(name, a, b))
                for a, b in zip(left["populations"][population]["scores"][scope]["per_class"],
                                right["populations"][population]["scores"][scope]["per_class"]):
                    for name in ("precision", "recall", "f1"):
                        per_class.append({**delta(name, a[name], b[name], class_id=a["label"]),
                                          "class_id": left["classes"][a["label"]]["id"], "class_name": left["classes"][a["label"]]["name"]})
                for a, b in zip(left["populations"][population]["folds"], right["populations"][population]["folds"]):
                    for name in NAMES:
                        folds.append({**delta(name, a[scope][name], b[scope][name], fold_id=a["fold_index"]), "fold_index": a["fold_index"]})
        obs = [store.artifact(identifier, "observations", fields=["y", "raw_pred", "confidence", "groups"])
               for identifier in (left_id, right_id)]
        from .metrics import _vote
        for population in ("all_labeled", "accepted"):
            predictions = [r["raw_pred"].copy() for r in obs]
            if population == "accepted":
                for ev, data, prediction in zip((left, right), obs, predictions):
                    prediction[data["confidence"] < ev["threshold"]] = -2
            for scope in ("pixel", "sample"):
                true = obs[0]["y"]
                values = predictions
                if scope == "sample":
                    groups = obs[0]["groups"]
                    true = np.asarray([_vote(true[groups == g]) for g in np.unique(groups)])
                    values = [np.asarray([_vote(p[(groups == g) & (p >= 0)]) if np.any((groups == g) & (p >= 0)) else -2
                                          for g in np.unique(groups)]) for p in predictions]
                states = [np.where(p < 0, 2, (p == true).astype(int)) for p in values]
                matrix = np.bincount(states[0]*3+states[1], minlength=9).reshape(3, 3)
                paired.append({"population": population, "scope": scope, "state_order": ["incorrect", "correct", "rejected"],
                               "rows": "current", "columns": "comparison", "counts": matrix.tolist(), "n": len(true)})
    result = {"evaluation_id": left_id, "comparison_id": right_id, "comparable": not differences,
              "checks": checks, "differences": differences, "rows": rows, "per_class": per_class, "folds": folds, "paired": paired,
              "evaluations": [{"evaluation_id": ev["evaluation_id"], "run_id": ev["run_id"], "protocol": ev["protocol"],
                               "threshold": ev["threshold"], "classes": ev["classes"], "populations": ev["populations"],
                               "cubes": ev["cubes"], "input_identity": ev["input_identity"]} for ev in (left, right)],
              "limitation": "只描述观察差值；没有消融或统计检验，不能作波段因果归因或声称显著。"}
    store.cache(left_id, "comparison-" + right_id, result)
    return result


def interpretation(store, identifier, comparison_id=None):
    ev = store.get(identifier)
    claims = []
    for scope in ("pixel", "sample"):
        score = ev["populations"]["accepted"]["scores"][scope]
        for name in (*NAMES, "coverage"):
            identity = {"population": "accepted", "scope": scope, "name": name, "class_id": None, "fold_id": None,
                        "aggregation": "pooled"}
            ref = score["metric_refs"].get(encode(identity))
            # All rendering values come from persisted evidence, not free-form arithmetic.
            with connect_database(store.database) as db:
                metric = db.execute("SELECT value FROM evaluation_metric WHERE id=? AND evaluation_id=?", (ref, identifier)).fetchone()
            if metric is None or metric[0] != score[name]:
                raise ModelingError("EVIDENCE_INTEGRITY_ERROR", "指标引用缺失或值不一致")
            claims.append({"kind": "fact", "scope": scope, "name": name, "value": metric[0], "metric_id": ref,
                           "run_id": ev["run_id"], "evaluation_id": identifier,
                           "text": scope + "接纳子集 " + name + ("：未获得数值结果" if metric[0] is None else "：" + format(metric[0], ".6g"))})
    def diagnostic(name, value, text, **identity):
        ref = store.scalar(identifier, {"name": name, "aggregation": "diagnostic", **identity}, value)
        claims.append({"kind": "fact", "scope": "pixel", "name": name, "value": value, "metric_id": ref,
                       "run_id": ev["run_id"], "evaluation_id": identifier,
                       "text": text+("：未获得数值结果" if value is None else "："+format(value, ".6g"))})
    for key, text in (("best_lv", "内层RMSECV最小建议LV"), ("elbow_lv", "内层容差建议LV"), ("selected_lv", "最终使用LV")):
        if ev.get("lv"):
            diagnostic(key, ev["lv"][key], text)
    diagnostic("threshold", ev["threshold"], "当前拒识阈值（未校准得分）")
    for error in ev['populations']['accepted']['scores']['pixel']['top_errors'][:5]:
        names = ev['classes'][error['true_label']]['name']+' → '+ev['classes'][error['predicted_label']]['name']
        dims = {'true_label': error['true_label'], 'predicted_label': error['predicted_label'], 'population': 'accepted'}
        diagnostic('confusion_count', error['count'], '主要误分 '+names+' 像素数', **dims)
        diagnostic('confusion_row_fraction', error['row_fraction'], names+' 占接纳真实类比例', **dims)
    result = {"evaluation_id": identifier, "generator": "deterministic_evidence_summary", "cloud_called": False,
              "claims": claims, "limitations": ev["limitations"] + [
                  "接纳精度必须与覆盖率一起判断；多数投票只描述主类。",
                  "LV曲线与重要性不能证明容量不足/充足或化学因果关系。"],
              "suggestions": ["优先核查主要双向误分与低支持类别。", "部署阈值仅在内层或独立校准数据选取。"],
              "hypotheses": [], "token_usage": None, "audit_id": None}
    if comparison_id:
        result["comparison"] = compare(store, identifier, comparison_id)
        for row in result['comparison']['rows']:
            if row['population'] == 'accepted' and row['name'] in ('oa', 'kappa'):
                claims.append({'kind': 'fact', 'scope': row['scope'], 'name': 'difference_'+row['name'],
                    'value': row['difference'], 'metric_id': row['metric_id'], 'run_id': ev['run_id'], 'evaluation_id': identifier,
                    'text': row['scope']+' 接纳子集 '+row['name']+' 当前减对比（原单位）'+
                    ('：未获得数值结果' if row['difference'] is None else '：'+format(row['difference'], '.6g'))})
    store.cache(identifier, "interpretation-" + (comparison_id or "current"), result)
    return result


def cloud_interpretation(store, identifier, comparison_id=None, client=None):
    """The LLM selects and orders evidence; numeric rendering remains deterministic."""
    import json
    from spectrumagent.agent.llm import OpenAICompatibleClient, read_settings, LLMError, _egress_blocked
    settings = read_settings(store.database)
    kind = "interpretation-cloud-" + digest({"model": settings.model, "provider": settings.base_url,
                                            "template": 1, "comparison_id": comparison_id})[:16]
    if client is None:
        try:
            return store.artifact(identifier, kind)
        except ModelingError as error:
            if error.code != "ARTIFACT_NOT_FOUND":
                raise
    result = interpretation(store, identifier, comparison_id)
    candidates = {c["metric_id"]: c["text"] for c in result["claims"]}
    payload = {c["metric_id"]: c["value"] for c in result["claims"]}
    suggestions = {"review_confusions": "优先复核主要误分类别与相应原始光谱。",
                   "check_coverage": "同时判断接纳精度和覆盖率，避免过高阈值掩盖错误。",
                   "independent_validation": "增加独立物理样品验证，保留分组和类别支持记录。"}
    messages = [{"role": "system", "content": "你解读分类评价。仅从给定事实ID和建议ID中选择并排序，禁止创造数值和事实。"
                 "返回JSON对象，字段fact_ids为事实ID列表，suggestion_ids为建议ID列表。"},
                {"role": "user", "content": encode({"run_id": result["claims"][0]["run_id"], "evaluation_id": identifier,
                 "metric_values": payload, "facts": candidates, "suggestions": suggestions})}]
    if _egress_blocked(messages):
        result.update(cloud_attempted=False, cloud_error="EGRESS_BLOCKED")
        return result
    client = client or OpenAICompatibleClient(store.database, default_timeout=60)
    try:
        response = client.chat(messages, [])
        parsed = json.loads(response.content or "")
        facts, advice = parsed["fact_ids"], parsed["suggestion_ids"]
        if (not isinstance(facts, list) or not facts or len(facts) > len(candidates) or any(not isinstance(i, str) or i not in candidates for i in facts)
                or not isinstance(advice, list) or len(advice) > len(suggestions) or any(not isinstance(i, str) or i not in suggestions for i in advice)):
            raise ValueError("unreferenced claim")
        selected = {c["metric_id"]: c for c in result["claims"]}
        result.update(claims=[selected[i] for i in dict.fromkeys(facts)], suggestions=[suggestions[i] for i in dict.fromkeys(advice)],
                      generator="cloud_evidence_selection", cloud_called=True, cloud_attempted=True,
                      token_usage=response.usage.model_dump() if response.usage else None,
                      audit_id=getattr(client, "last_audit_id", None) if isinstance(getattr(client, "last_audit_id", None), str) else None, model=read_settings(store.database).model,
                      egress_fields=["run_id", "evaluation_id", "metric_values", "facts", "suggestions"])
    except (LLMError, ValueError, KeyError, TypeError) as error:
        result.update(cloud_attempted=True, cloud_error=getattr(error, "code", "UNREFERENCED_MODEL_OUTPUT"),
                      audit_id=getattr(client, "last_audit_id", None) if isinstance(getattr(client, "last_audit_id", None), str) else None)
    if result["cloud_called"]:
        store.cache(identifier, kind, result)
    return result
