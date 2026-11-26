"""PLS-DA v2: nested grouped selection, frozen transformations and OOF positions."""
import json
from pathlib import Path, PurePosixPath
from time import perf_counter
from uuid import uuid4
import warnings
from contextlib import nullcontext

import numpy as np

from backend.database import connect_database
from spectrumagent.annotation.engines.superpixels import ReadableRows, row_blocks
from spectrumagent.preprocess import builtin_registry
from spectrumagent.preprocess.run import code_version
from spectrumagent.storage import guard as storage
from . import ModelingError
from .cv import plan_folds
from .dataset import _inputs
from .evaluation import Evaluations, encode, digest, stamp, summarize
from .inference import apply_with_calibration
from .leak import skipped_training_report
from .training_state import CURRENT, TrainingCancelled, checkpoint, emit, stage


def file_sha256(path):
    import hashlib
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            checkpoint()
            result.update(block)
    return result.hexdigest()


def load_data(registry, paths, rows, sample_groups=None):
    checkpoint()
    if sample_groups is not None and (set(sample_groups) != {r["cube_id"] for r in rows}
                                      or any(not isinstance(v, str) or not v for v in sample_groups.values())):
        raise ModelingError("INVALID_GROUP_MAPPING", "样品映射须完整覆盖本次图像")
    with connect_database(registry.database) as db:
        control = CURRENT.get()
        if control:
            actual = [list(r) for r in db.execute('SELECT id,code,name,color_hex,is_background,sort_order FROM label ORDER BY sort_order,code,id')]
            if actual != control.binding['catalog']:
                raise ModelingError('TRAINING_REFERENCE_CHANGED', '受理后类别目录变化，请重新提交')
        catalog = {r[0]: {"id": r[0], "code": r[1], "name": r[2], "color": r[3], "background": bool(r[4])}
                   for r in db.execute("SELECT id,code,name,color_hex,is_background FROM label ORDER BY sort_order,code,id")}
    pipes = {digest(r["pipeline"]) for r in rows}
    if len(pipes) != 1:
        raise ModelingError("PIPELINE_MISMATCH", "单个冻结分类模型要求各成员使用相同有效配方")
    chunks, cubes, all_ids, wave_key = [], [], set(), None
    groups = {v: i for i, v in enumerate(sorted({sample_groups[r["cube_id"]] if sample_groups else r["cube_id"] for r in rows}))}
    for cube_index, row in enumerate(rows):
        cube = row["cube_id"]
        emit('source_verify', image_index=cube_index, total_images=len(rows), cube_id=cube)
        dataset, _ = registry.readable(cube, raw=False)
        hashes = {"header": file_sha256(Path(dataset.header_path)), "data": file_sha256(Path(dataset.data_path))}
        shape = tuple(dataset.shape)
        waves = list(dataset.wavelengths)
        unit = next((str(v) for k, v in dataset.metadata.items()
                     if k.lower().replace(" ", "").replace("_", "") == "wavelengthunits"), None)
        key = encode([shape[2], waves, unit])
        if wave_key is not None and key != wave_key:
            raise ModelingError("FEATURE_AXIS_MISMATCH", "各图像输入波长轴、单位和维度必须一致")
        wave_key = key
        relative = PurePosixPath(row["annotation"]["snapshot_ref"])
        base = paths.snapshots.resolve()
        folder = base.joinpath(*relative.parts).resolve()
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative) or ":" in str(relative) or not folder.is_relative_to(base):
            raise ModelingError("INVALID_SNAPSHOT_REF", "标注快照引用非法")
        with np.load(folder / "label_map.npz", allow_pickle=False) as a:
            label_map = a["label_map"].copy()
        mapping = json.loads((folder / "label_index.json").read_text("utf-8"))
        if label_map.shape != shape[:2] or label_map.dtype.kind not in "iu" or np.any(label_map < -2):
            raise ModelingError("INVALID_LABEL_MAP", "标注形状或编码非法")
        needed = np.unique(label_map[label_map >= 0])
        for local in needed:
            if mapping.get(str(int(local))) not in catalog:
                raise ModelingError("LABEL_MAPPING_INVALID", "快照类别身份不存在")
        ids = {int(local): mapping[str(int(local))] for local in needed}
        all_ids.update(ids.values())
        selected = np.flatnonzero(label_map.ravel() >= 0)
        x = np.empty((len(selected), shape[2]), dtype=np.float64)
        offset = 0
        for first in range(0, shape[0], 32):
            checkpoint()
            last = min(shape[0], first+32)
            block = dataset.read_region(first, last, 0, shape[1])
            mask = label_map[first:last].ravel() >= 0
            n = int(mask.sum())
            x[offset:offset+n] = block.reshape(-1, shape[2])[mask]
            offset += n
            emit('dataset', image_index=cube_index, total_images=len(rows), rows_read=last, total_rows=shape[0], labeled_read=offset)
        valid = np.isfinite(x).all(axis=1)
        if not valid.any():
            raise ModelingError("NO_VALID_LABELED_SPECTRA", "图像没有有限的已标光谱")
        group = groups[sample_groups[cube] if sample_groups else cube]
        local_labels = label_map.ravel()[selected][valid]
        chunk = {"X": x[valid], "label_ids": [ids[int(v)] for v in local_labels],
                 "groups": np.full(int(valid.sum()), group, np.int32),
                 "cube_index": np.full(int(valid.sum()), cube_index, np.int32), "flat_index": selected[valid]}
        chunks.append(chunk)
        current = {"header": file_sha256(Path(dataset.header_path)), "data": file_sha256(Path(dataset.data_path))}
        if current != hashes:
            raise ModelingError("SOURCE_CHANGED", "读取训练输入期间源文件变化")
        from spectrumagent.preprocess.recipes import input_fingerprint, annotation_identity
        import os
        sources = [Path(dataset.header_path), Path(dataset.data_path)]
        source_base = Path(os.path.commonpath([str(p.parent) for p in sources]))
        source_fingerprints = {p.relative_to(source_base).as_posix(): file_sha256(p) for p in sorted(set(sources))}
        expected = input_fingerprint(cube, source_fingerprints, row["annotation"]["id"]+":"+annotation_identity(label_map,mapping), len(selected))
        if expected != row["run"]["input_fingerprint"]:
            raise ModelingError("TRAINING_REFERENCE_CHANGED", "当前源和标注身份与预处理引用不一致")
        cubes.append({"cube_id": cube, "group": group, "shape": list(shape), "name": dataset.name,
                      "group_ref": sample_groups[cube] if sample_groups else cube,
                      "annotation_version_id": row["annotation"]["id"], "snapshot_hash": file_sha256(folder / "label_map.npz"),
                      "label_index_hash": file_sha256(folder / "label_index.json"), "source_hashes": hashes,
                      "input_fingerprint": row["run"]["input_fingerprint"], "pipeline": row["pipeline"],
                      "n_valid": int(valid.sum()), "invalid_spectra": int((~valid).sum()),
                      "unlabeled": int((label_map == -1).sum()), "annotation_uncertain": int((label_map == -2).sum())})
        emit('dataset_image', completed=cube_index+1, total=len(rows), valid=int(valid.sum()), invalid=int((~valid).sum()),
             unlabeled=int((label_map == -1).sum()), annotation_uncertain=int((label_map == -2).sum()))
    class_ids = [v for v in catalog if v in all_ids]
    classes = [{**catalog[v], "label": i} for i, v in enumerate(class_ids)]
    index = {v: i for i, v in enumerate(class_ids)}
    if len(classes) < 2:
        raise ModelingError("INSUFFICIENT_CLASSES", "PLS-DA至少需要两个有效类别")
    X = np.concatenate([c["X"] for c in chunks])
    y = np.asarray([index[v] for c in chunks for v in c["label_ids"]], dtype=np.int64)
    if not len(y):
        raise ModelingError("NO_LABELED_PIXELS", "没有有限的有真值光谱")
    return {"X": X, "y": y, **{k: np.concatenate([c[k] for c in chunks]) for k in ("groups", "cube_index", "flat_index")},
            "classes": classes, "cubes": cubes, "wavelengths": waves, "wavelength_unit": unit,
            "pipeline": rows[0]["pipeline"], "group_kind": "physical_sample" if sample_groups else "cube_proxy"}


def fit_transform(X, pipeline, waves):
    checkpoint()
    from .registry import normalized_pipeline
    pipeline = normalized_pipeline(pipeline)
    transformed = builtin_registry().run(X, pipeline, wavelengths=waves or None)
    if not np.isfinite(transformed.spectra).all():
        raise ModelingError("NON_FINITE_SPECTRA", "预处理结果含非有限值，请调整配方")
    state = {"protocol": 1, "pipeline": pipeline, "steps": transformed.steps, "input_n_features": X.shape[1]}
    return transformed.spectra, state, transformed.wavelengths


def predict(features, model):
    values = (features - np.asarray(model["x_mean"])) @ np.asarray(model["coef"]).T + np.asarray(model["intercept"])
    if not np.isfinite(values).all():
        raise ModelingError("INVALID_MODEL_ARTIFACT", "分类模型产生非有限值")
    weights = np.exp(values-values.max(axis=1, keepdims=True))
    return weights/weights.sum(axis=1, keepdims=True)


def model_record(model):
    return {"coef": model.coef_.tolist(), "intercept": model.intercept_.tolist(),
            "x_mean": model._x_mean.tolist(), "selected_lv": model.n_components}


def _fit(X, hot, lv):
    from sklearn.cross_decomposition import PLSRegression

    checkpoint()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = PLSRegression(n_components=lv).fit(X, hot)
    from sklearn.exceptions import ConvergenceWarning
    if any(issubclass(w.category, ConvergenceWarning) for w in caught):
        emit('fit_warning', code='CONVERGENCE_WARNING', lv=lv)
    if not np.isfinite(model.coef_).all():
        raise ModelingError("DEGENERATE_MODEL", "候选模型系数非有限")
    return model


def _class_counts(y, groups, labels):
    return [{"label": int(label), "pixels": int(np.count_nonzero(y == label)),
             "groups": int(len(np.unique(groups[y == label])))} for label in labels]


def _fold_support(y, groups, labels, fold):
    counts = _class_counts(y[fold["train_idx"]], groups[fold["train_idx"]], labels)
    return {"fold_index": fold["fold_index"], "train_classes": counts,
            "missing_train_labels": [c["label"] for c in counts if not c["pixels"]]}


def class_support_report(y, groups, classes, outer, *, protocol, seed):
    """Describe coverage without imposing a minimum number of groups per class."""
    labels = np.asarray([c["label"] for c in classes])
    def selection(a):
        selected_y, selected_groups = y[a], groups[a]
        count = len(np.unique(selected_groups))
        if count < 2:
            return []
        folds = plan_folds(selected_y, selected_groups, task="classification", strategy="group_kfold",
                           folds=min(3, count), seed=seed)
        return [_fold_support(selected_y, selected_groups, labels, f) for f in folds]
    final_inner = selection(np.arange(len(y)))
    outer_support = [{**_fold_support(y, groups, labels, f),
                      "inner_folds": selection(f["train_idx"]) if protocol == "nested_group_cv" else []}
                     for f in outer]
    missing_outer = sum(bool(f["missing_train_labels"]) for f in outer_support)
    missing_inner = sum(bool(f["missing_train_labels"]) for f in final_inner
                        + [inner for f in outer_support for inner in f["inner_folds"]])
    warnings = []
    if missing_outer or missing_inner:
        warnings.append(f"允许缺类训练：{missing_outer} 个外层训练折、{missing_inner} 个内层选优训练折缺少类别。"
                        "缺失类别在相应训练折无学习样本；评价保留全部类别和验证像素，请结合类别覆盖情况解读指标。")
    return {"policy": "allow_missing_classes", "minimum_groups_per_class": None,
            "classes": [{**c, **counts} for c, counts in zip(classes, _class_counts(y, groups, labels))],
            "outer_folds": outer_support, "final_inner_folds": final_inner, "warnings": warnings}


def choose(X, y, groups, pipeline, waves, labels, *, seed, maximum, manual, ipls):
    count = len(np.unique(groups))
    if count < 2:
        raise ModelingError("INSUFFICIENT_NESTED_GROUPS", "内层选优至少需要两个训练样品组")
    inner = plan_folds(y, groups, task="classification", strategy="group_kfold", folds=min(3, count), seed=seed)
    # Absent classes keep their global output columns and held-out truth remains scored.
    hot = (y[:, None] == labels).astype(float)
    cached = []
    for f in inner:
        a, b = f["train_idx"], f["test_idx"]
        emit('inner_preprocess', inner_fold=f['fold_index'], total_inner=len(inner))
        train, state, _ = fit_transform(X[a], pipeline, waves)
        test = apply_with_calibration(state, pipeline, X[b])
        rank = int(np.linalg.matrix_rank(train-train.mean(axis=0)))
        cached.append((f, train, test, max(0, min(len(a)-1, train.shape[1], rank))))
    upper = min(maximum or 20, *(c[3] for c in cached))
    if upper < 1 or manual is not None and manual > upper:
        raise ModelingError("INVALID_LV", "LV超出内层训练数据有效秩", maximum=upper)
    p = cached[0][1].shape[1]
    if any(c[1].shape[1] != p for c in cached):
        raise ModelingError("FEATURE_COUNT_MISMATCH", "折内变换输出维度不一致")
    def evaluate(cols, lv):
        errors, fold_rmse = [], []
        for f, train, test, _ in cached:
            checkpoint()
            model = _fit(train[:, cols], hot[f["train_idx"]], lv)
            residual = model.predict(test[:, cols])-hot[f["test_idx"]]
            errors.append(residual.ravel()**2)
            fold_rmse.append(float(np.sqrt(np.mean(residual**2))))
        return {"n_components": lv, "rmsecv": float(np.sqrt(np.mean(np.concatenate(errors)))),
                "sd": float(np.std(fold_rmse, ddof=1))}
    def sweep(cols, upper, selection):
        curve = []
        for candidate in range(1, upper+1):
            began = perf_counter()
            value = evaluate(cols, candidate)
            curve.append(value)
            emit('lv', selection=selection, completed=candidate, total=upper, lv=candidate,
                 rmsecv=value['rmsecv'], unit_seconds=perf_counter()-began)
        return curve
    curve = sweep(np.arange(p), upper, 'full')
    best = min(curve, key=lambda r: (r["rmsecv"], r["n_components"]))
    columns, bands = np.arange(p), None
    if ipls:
        if p < 20:
            raise ModelingError("INSUFFICIENT_IPLS_FEATURES", "iPLS要求至少20个变换后特征")
        intervals = np.array_split(columns, 20)
        scan_lv = min(best["n_components"], min(map(len, intervals)))
        scan = []
        for i, cols in enumerate(intervals):
            began = perf_counter()
            value = {"index": i+1, "start_col": int(cols[0])+1, "end_col": int(cols[-1])+1, **evaluate(cols, scan_lv)}
            scan.append(value)
            emit('ipls', completed=i+1, total=len(intervals), start_col=value['start_col'], end_col=value['end_col'],
                 rmsecv=value['rmsecv'], unit_seconds=perf_counter()-began, feature_count=len(cols),
                 remaining_features=sum(map(len, intervals[i+1:])))
        chosen = sorted(sorted(scan, key=lambda r: (r["rmsecv"], r["index"]))[:6], key=lambda r: r["index"])
        columns = np.concatenate([intervals[r["index"]-1] for r in chosen])
        upper = min(upper, len(columns))
        if manual is not None and manual > upper:
            raise ModelingError("INVALID_LV", "手动LV超出选中特征数")
        curve = sweep(columns, upper, 'selected')
        best = min(curve, key=lambda r: (r["rmsecv"], r["n_components"]))
        bands = {"method": "ipls", "n_intervals": 20, "keep": 6, "lv": scan_lv, "curve": scan,
                 "intervals": chosen, "indices": columns.tolist(), "definition": "仅内层选优；最终模型应用所选列",
                 "limitation": "折间选择可不同；变换后特征不必对应原始波长"}
    lv = manual if manual is not None else best["n_components"]
    elbow = next(r["n_components"] for r in curve if r["rmsecv"] <= best["rmsecv"]+best["sd"])
    train, state, axis = fit_transform(X, pipeline, waves)
    emit('fit', lv=lv, feature_count=len(columns))
    model = _fit(train[:, columns], hot, lv)
    sweep = {"curve": curve, "best_lv": best["n_components"], "elbow_lv": elbow, "selected_lv": lv,
             "by_cv_min": best["n_components"], "by_elbow": elbow, "manual_override": manual is not None,
             "definition": "inner grouped one-hot RMSECV; tolerance candidate <= minimum + one fold SD; not curvature/1SE"}
    return {"model": model_record(model), "calibration": state, "columns": columns.tolist(),
            "feature_axis": axis.tolist() if axis is not None else None, "bands": bands, "lv": sweep,
            "inner_splits": [{**{k: v for k, v in f.items() if k not in ("train_idx", "test_idx")},
                              **_fold_support(y, groups, labels, f)} for f in inner]}


def train(engine, rows, *, cv_folds, seed, threshold, maximum, manual, ipls, protocol,
          training_set_ref=None, dataset_version_ref=None, sample_groups=None):
    started = perf_counter()
    data = load_data(engine.registry, engine.paths, rows, sample_groups)
    control = CURRENT.get()
    X, y, groups = (data[k] for k in ("X", "y", "groups"))
    labels = np.arange(len(data["classes"]))
    outer = plan_folds(y, groups, task="classification", strategy="group_kfold", folds=cv_folds, seed=seed)
    if protocol == "nested_group_cv" and any(len(f["train_groups"]) < 2 for f in outer):
        raise ModelingError("INSUFFICIENT_NESTED_GROUPS", "外层训练侧至少需两个组用于内层选优")
    report = skipped_training_report()
    report["class_support"] = class_support_report(y, groups, data["classes"], outer, protocol=protocol, seed=seed)
    report["group_kind"] = data["group_kind"]
    report["preprocess_full_fit"] = {"acknowledged": False, "affected_steps": [], "reason": "所有数据拟合仅限各层训练侧"}
    emit('check', status=report['status'], warnings=report['class_support']['warnings'])
    if control:
        control.prepare(data, outer, protocol, threshold, report['class_support'])
    identifier = str(uuid4())
    params = {"n_samples": len(np.unique(groups)), "n_pixels_used": len(y), "evaluation_protocol": protocol,
              "confidence_threshold": threshold, "operator": {"name": "train_plsda", "version": 2}}
    with connect_database(engine.database) as db:
        db.execute("INSERT INTO training_run (id,cube_ids,annotation_version_ids,preprocess_run_ids,task,target,cv_strategy,"
                   "cv_folds,seed,model_family,model_params,status,created_at,split_strategy) VALUES (?,?,?,?,'classification',"
                   "'label','group_kfold',?,?,'plsda',?,'running',?,'none')",
                   (identifier, encode([r["cube_id"] for r in rows]), encode([r["annotation"]["id"] for r in rows]),
                    encode([r["run"]["id"] for r in rows]), cv_folds, seed, encode(params), stamp()))
        db.executemany("INSERT INTO training_fold VALUES (?,?,?,?,?,?,?)",
                       [(str(uuid4()), identifier, f["fold_index"], len(f["train_idx"]), len(f["test_idx"]),
                         encode(f["train_groups"]), encode(f["test_groups"])) for f in outer])
    store = Evaluations(engine.registry, engine.paths)
    try:
        emit('run', run_id=identifier, total_pixels=len(y), total_folds=len(outer))
        probs = np.empty((len(y), len(labels)))
        baseline_probs = np.empty_like(probs) if ipls else None
        fold_index = np.empty(len(y), dtype=np.int32)
        fold_models = []
        restored = control.reuse('final') if control else None
        if restored:
            final = restored[0]
        else:
            with stage(branch='final', outer_fold=None):
                final = choose(X, y, groups, data["pipeline"], data["wavelengths"], labels,
                               seed=seed, maximum=maximum, manual=manual, ipls=ipls)
            if control:
                control.save('final', final)
        for f in outer:
            emit('outer', outer_fold=f['fold_index'], total=len(outer))
            a, b = f["train_idx"], f["test_idx"]
            unit = 'fold-'+str(f['fold_index'])+'-selected'
            restored = control.reuse(unit) if control else None
            if restored:
                pack, saved_observations = restored
                probs[b] = saved_observations['probabilities']
            elif protocol == "nested_group_cv":
                with stage(branch='selected', outer_fold=f['fold_index']):
                    pack = choose(X[a], y[a], groups[a], data["pipeline"], data["wavelengths"], labels,
                                  seed=seed, maximum=maximum, manual=manual, ipls=ipls)
            else:
                features, state, axis = fit_transform(X[a], data["pipeline"], data["wavelengths"])
                cols = final["columns"]
                pack = {**final, "calibration": state,
                        "model": model_record(_fit(features[:, cols], (y[a, None] == labels).astype(float), final["model"]["selected_lv"]))}
            if not restored:
                transformed = apply_with_calibration(pack["calibration"], data["pipeline"], X[b])
                probs[b] = predict(transformed[:, pack["columns"]], pack["model"])
                if control:
                    control.save(unit, pack, b, probs[b])
            fold_index[b] = f["fold_index"]
            fold_models.append({"fold_index": f["fold_index"], "train_groups": f["train_groups"],
                                "test_groups": f["test_groups"], **_fold_support(y, groups, labels, f), **pack})
            fold_report = summarize(y[b], probs[b].argmax(axis=1), groups[b], probs[b].max(axis=1),
                                    np.zeros(len(b), np.int32), labels=labels.tolist(), threshold=threshold)
            metrics = {population: {scope: {k: score[k] for k in ('oa', 'aa', 'kappa', 'macro_f1', 'accepted', 'total')}
                                   for scope, score in pop['scores'].items()}
                       for population, pop in fold_report['populations'].items()}
            emit('fold_complete', outer_fold=f['fold_index'], branch='selected', n_pixels=len(b), metrics=metrics)
            if ipls:
                unit = 'fold-'+str(f['fold_index'])+'-baseline'
                restored = control.reuse(unit) if control else None
                if restored:
                    base, saved_observations = restored
                    baseline_probs[b] = saved_observations['probabilities']
                else:
                    with stage(branch='full_baseline', outer_fold=f['fold_index']):
                        base = choose(X[a], y[a], groups[a], data["pipeline"], data["wavelengths"], labels,
                                      seed=seed, maximum=maximum, manual=manual, ipls=False)
                    bt = apply_with_calibration(base["calibration"], data["pipeline"], X[b])
                    baseline_probs[b] = predict(bt[:, base["columns"]], base["model"])
                    if control:
                        control.save(unit, base, b, baseline_probs[b])
                emit('baseline_complete', outer_fold=f['fold_index'])
        emit('summarize')
        predicted = labels[probs.argmax(axis=1)]
        evaluation = summarize(y, predicted, groups, probs.max(axis=1), fold_index, labels=labels.tolist(), threshold=threshold)
        comparison = None
        if ipls:
            baseline = summarize(y, labels[baseline_probs.argmax(axis=1)], groups, baseline_probs.max(axis=1),
                                 fold_index, labels=labels.tolist(), threshold=threshold)
            comparison = {scope: {name: {k: pop["scores"][scope][k] for k in ("oa", "kappa")}
                          for name, pop in (("full", baseline["populations"]["accepted"]),
                                            ("selected", evaluation["populations"]["accepted"]))} for scope in ("pixel", "sample")}
            final["bands"]["comparison"] = comparison
        identity = {"cubes": data["cubes"], "classes": data["classes"], "fold_index_hash": hashlib_array(fold_index),
                    "group_hash": hashlib_array(groups),
                    "truth_hash": hashlib_array(y), "position_hash": digest([hashlib_array(data[k]) for k in ("cube_index", "flat_index")])}
        snapshot = {**evaluation, "protocol": protocol, "group_kind": data["group_kind"], "classes": data["classes"],
                    "cubes": data["cubes"], "n_images": len(rows), "n_samples": params["n_samples"],
                    "n_pixels": len(y), "operator": "train_plsda", "operator_version": 2,
                    "seed": seed, "code_version": code_version(), "training_set_ref": training_set_ref,
                    "dataset_version_ref": dataset_version_ref, "input_identity": identity, "lv": final["lv"],
                    "fold_selected_lv": [{"fold_index": p["fold_index"], "selected_lv": p["model"]["selected_lv"]} for p in fold_models],
                    "bands": final["bands"], "feature_count": len(final["columns"]),
                    "class_support": report["class_support"],
                    "training_job_id": control.identifier if control else None,
                    "continued_from": control.parent if control else None,
                    "wavelength_unit": data["wavelength_unit"], "duration_s": perf_counter()-started,
                    "limitations": (["图像组代理物理样品；混合图的多数票只代表主类"] if not sample_groups else [])
                                   + report["class_support"]["warnings"]
                                   + (["探索性CV复用选优信息，不能作为独立泛化评价"] if protocol != "nested_group_cv" else [])}
        model_doc = {**final, "classes": data["classes"], "pipeline": data["pipeline"], "input_wavelengths": data["wavelengths"],
                     "wavelength_unit": data["wavelength_unit"], "confidence_threshold": threshold,
                     "feature_min": X.min(axis=0).tolist(), "feature_max": X.max(axis=0).tolist()}
        emit('publish')
        with control.publish() if control else nullcontext():
            snapshot = store.create(identifier, {**snapshot, 'complete': True}, documents={"model": model_doc, "fold_models": fold_models},
                matrices={"raw_spectra": X},
                arrays={"observations": {k: data[k] for k in ("y", "groups", "cube_index", "flat_index")} |
                                        {"probabilities": probs, "raw_pred": probs.argmax(axis=1), "confidence": probs.max(axis=1), "fold_index": fold_index}})
            params.update(selected_lv=final["model"]["selected_lv"], best_lv=final["lv"]["best_lv"], by_elbow=final["lv"]["elbow_lv"])
            with connect_database(engine.database) as db:
                db.execute("UPDATE training_run SET status='succeeded',finished_at=?,model_params=?,leak_report=? WHERE id=?",
                           (stamp(), encode(params), encode(report), identifier))
                scores = snapshot["populations"]["accepted"]["scores"]
                db.executemany("INSERT INTO metric VALUES (?,?,NULL,?,?,?,?)",
                    [(str(uuid4()), identifier, scope, k, scores[scope][k], stamp()) for scope in ("pixel", "sample") for k in ("oa", "kappa")])
        return result(snapshot, report)
    except BaseException as error:
        engine._transition(identifier, "cancelled" if isinstance(error, TrainingCancelled) else "failed", report=report,
                           error={"error": getattr(error, "code", type(error).__name__)})
        raise


def hashlib_array(values):
    import hashlib
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def result(snapshot, leak_report):
    report = snapshot["populations"]["accepted"]
    scores = report["scores"]
    lv = snapshot["lv"]
    return {"run_id": snapshot["run_id"], "status": "succeeded", "task": "classification", "group_by": snapshot["group_kind"],
            "cv_strategy": "group_kfold", "cv_folds": len(report["folds"]), "n_samples": snapshot["n_samples"],
            "n_pixels_used": snapshot["n_pixels"], "selected_lv": lv["selected_lv"], "best_lv": lv["best_lv"],
            "by_cv_min": lv["best_lv"], "by_elbow": lv["elbow_lv"],
            "metrics": {s: {k: scores[s][k] for k in ("oa", "kappa")} for s in ("pixel", "sample")},
            "confusion": {**report, "threshold": {"confidence_threshold": snapshot["threshold"],
                           "accepted_pixels": scores["pixel"]["accepted"], "uncertain_pixels": scores["pixel"]["rejected"],
                           "total_pixels": snapshot["n_pixels"]}, "lv": lv,
                          "manifest": {"operator": "train_plsda", "operator_version": 2, "seed": snapshot["seed"],
                                       "code_version": snapshot["code_version"]}},
            "bands": snapshot["bands"], "evaluation": snapshot, "leak_report": leak_report, "error": None}
