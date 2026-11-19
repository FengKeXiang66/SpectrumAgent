"""Session-local bounded batch execution and durable-to-session prediction artifacts."""
import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock, Event
from uuid import uuid4

import numpy as np
from backend.database import connect_database
from spectrumagent.storage import guard as storage
from spectrumagent.preprocess.run import file_sha256
from . import ModelingError
from .classification import predict
from .classification_models import ClassificationModels
from .evaluation import encode, digest, stamp, Evaluations
from .inference import apply_with_calibration, png_rgb


def source_signature(dataset):
    return [{"size": Path(p).stat().st_size, "mtime_ns": Path(p).stat().st_mtime_ns}
            for p in (dataset.header_path, dataset.data_path)]


class ClassificationInference:
    def __init__(self, registry, paths):
        self.registry, self.paths, self.database = registry, paths, registry.database
        self.models = ClassificationModels(registry, paths)
        self.lock, self.jobs, self.keys = Lock(), {}, {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="classification")

    def submit(self, model_id, cube_ids, threshold=None):
        model = self.models.get(model_id, calibration=True)
        if not cube_ids or len(cube_ids) > 1000 or len(set(cube_ids)) != len(cube_ids):
            raise ModelingError("INVALID_INFERENCE_SCOPE", "批量范围须为1至1000个不重复图像")
        pack = model["calibration"]
        threshold = pack["confidence_threshold"] if threshold is None else threshold
        if not 0 <= threshold < 1:
            raise ModelingError("INVALID_CONFIDENCE_THRESHOLD", "阈值须在[0,1)")
        targets = []
        for cube_id in cube_ids:
            dataset, _ = self.registry.readable(cube_id, raw=False)
            with connect_database(self.database) as db:
                project = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (cube_id,)).fetchone()
            if not project or project[0] != model["project_id"]:
                raise ModelingError("PROJECT_MISMATCH", "新数据须属于模型项目")
            if dataset.shape[2] != pack["calibration"]["input_n_features"] or list(dataset.wavelengths) != pack["input_wavelengths"]:
                raise ModelingError("FEATURE_AXIS_MISMATCH", "新图输入波长轴或维度不匹配")
            unit = next((str(v) for k, v in dataset.metadata.items()
                         if k.lower().replace(" ", "").replace("_", "") == "wavelengthunits"), None)
            if unit != pack["wavelength_unit"]:
                raise ModelingError("FEATURE_AXIS_MISMATCH", "新图波长单位不匹配")
            signature = source_signature(dataset)
            hashes = {k: file_sha256(Path(p)) for k, p in (("header", dataset.header_path), ("data", dataset.data_path))}
            if signature != source_signature(dataset):
                raise ModelingError("SOURCE_CHANGED", "固定推理范围时源文件变化")
            targets.append({"cube_id": cube_id, "signature": signature, "source_hashes": hashes})
        key = digest({"model": model_id, "hash": model["model_hash"], "targets": targets, "threshold": threshold})
        with self.lock:
            if key in self.keys:
                return self.snapshot(self.keys[key])
            if sum(j["status"] in ("queued", "running") for j in self.jobs.values()) >= 16:
                raise ModelingError("BUSY", "分类后台队列已满")
            # Retain at most 64 terminal receipts; no restart/resume promise.
            terminal = [i for i, j in self.jobs.items() if j["status"] not in ("queued", "running")]
            while len(self.jobs) >= 64 and terminal:
                removed = terminal.pop(0)
                self.jobs.pop(removed)
                self.keys = {k: v for k, v in self.keys.items() if v != removed}
            identifier = str(uuid4())
            job = {"task_id": identifier, "status": "queued", "model_id": model_id, "threshold": threshold,
                   "evaluation_id": model["evaluation_id"], "kind": "inference",
                   "items": [{"cube_id": t["cube_id"], "status": "pending"} for t in targets],
                   "targets": targets, "cancel": Event(), "created_at": stamp()}
            self.jobs[identifier], self.keys[key] = job, identifier
            self.executor.submit(self._work, identifier, model)
            return self.snapshot(identifier)

    def _work(self, identifier, model):
        try:
            with self.registry.recycle.coordinator.job():
                self._work_guarded(identifier, model)
        except Exception as error:
            with self.lock:
                self.jobs[identifier].update(status="failed", error=getattr(error, "code", type(error).__name__))

    def _work_guarded(self, identifier, model):
        with self.lock:
            job = self.jobs[identifier]
            job["status"] = "running"
        for i, target in enumerate(job["targets"]):
            if job["cancel"].is_set():
                break
            with self.lock:
                job["items"][i]["status"] = "running"
            try:
                result = self.single(model, target, job["threshold"])
                with self.lock:
                    job["items"][i].update(status="succeeded", **result)
            except Exception as error:
                with self.lock:
                    job["items"][i].update(status="failed", error=getattr(error, "code", type(error).__name__))
        with self.lock:
            finished = [r["status"] for r in job["items"]]
            if job["cancel"].is_set():
                job["status"] = "cancelled"
            elif all(s == "succeeded" for s in finished):
                job["status"] = "succeeded"
            elif any(s == "succeeded" for s in finished):
                job["status"] = "partial"
            else:
                job["status"] = "failed"

    def snapshot(self, identifier, offset=0, limit=50):
        job = self.jobs.get(identifier)
        if not job:
            raise ModelingError("TASK_NOT_FOUND", "任务回执已失效；仅当前会话有效")
        counts = {s: sum(r["status"] == s for r in job["items"]) for s in ("pending", "running", "succeeded", "failed")}
        totals = {"total_pixels": 0, "valid_pixels": 0, "accepted": 0, "rejected": 0, "out_of_domain": 0}
        classes = {}
        for item in job["items"]:
            for name in totals:
                totals[name] += item.get("stats", {}).get(name, 0)
            for row in item.get("stats", {}).get("classes", []):
                classes[row["label"]] = classes.get(row["label"], 0) + row["count"]
        return {"task_id": identifier, "status": job["status"], "model_id": job["model_id"], "total": len(job["items"]),
                "evaluation_id": job["evaluation_id"], "kind": job["kind"], "result": job.get("result"), "error": job.get("error"),
                "phase": job.get("phase", job["status"]),
                "counts": counts, "items": [dict(r) for r in job["items"][offset:offset+limit]], "offset": offset, "limit": limit,
                "summary": {**totals, "classes": [{"label": k, "count": v} for k, v in sorted(classes.items())]},
                "limitation": "会话内任务；关闭应用后不承诺续跑；没有真值不报告准确率。"}

    def status(self, identifier, offset=0, limit=50):
        with self.lock:
            return self.snapshot(identifier, offset, limit)

    def calculate(self, evaluation_id, kind, key, action, contextual=False):
        key = digest({"evaluation": evaluation_id, "kind": kind, "key": key})
        with self.lock:
            if key in self.keys and self.jobs[self.keys[key]]["status"] not in ("failed", "cancelled"):
                return self.snapshot(self.keys[key])
            if sum(j["status"] in ("queued", "running") for j in self.jobs.values()) >= 16:
                raise ModelingError("BUSY", "后台队列已满")
            terminal = [i for i, j in self.jobs.items() if j["status"] not in ("queued", "running")]
            while len(self.jobs) >= 64 and terminal:
                removed = terminal.pop(0)
                self.jobs.pop(removed)
                self.keys = {k: v for k, v in self.keys.items() if v != removed}
            identifier = str(uuid4())
            self.keys[key] = identifier
            self.jobs[identifier] = {"task_id": identifier, "status": "queued", "model_id": None, "items": [],
                                    "evaluation_id": evaluation_id, "kind": kind, "cancel": Event()}
        def work():
            with self.lock:
                job = self.jobs[identifier]
                job["status"] = "running"
            def checkpoint(phase):
                with self.lock:
                    job["phase"] = phase
                if job["cancel"].is_set():
                    raise ModelingError("TASK_CANCELLED", "导出已取消，未发布结果")
            try:
                if not job["cancel"].is_set():
                    with self.registry.recycle.coordinator.job():
                        result = action(checkpoint) if contextual else action()
                    with self.lock:
                        job["result"] = result
                        job["status"] = "succeeded"
                with self.lock:
                    if job["cancel"].is_set():
                        job["status"] = "cancelled"
            except Exception as error:
                with self.lock:
                    job["status"] = "cancelled" if job["cancel"].is_set() else "failed"
                    job["error"] = ("DEPENDENCY_UNAVAILABLE:"+str(error.name) if isinstance(error, ModuleNotFoundError)
                                    else getattr(error, "code", type(error).__name__))
        self.executor.submit(work)
        return self.status(identifier)

    def cancel(self, identifier):
        with self.lock:
            if identifier not in self.jobs:
                raise ModelingError("TASK_NOT_FOUND", "任务不存在")
            job = self.jobs[identifier]
            if job["status"] not in ("queued", "running") or job["kind"] == "export" and job.get("phase") == "publish":
                return self.snapshot(identifier)
            self.jobs[identifier]["cancel"].set()
            return self.snapshot(identifier)

    def retry(self, identifier):
        with self.lock:
            job = self.jobs.get(identifier)
            if not job or job["status"] in ("queued", "running") or job["kind"] != "inference":
                raise ModelingError("TASK_NOT_RETRYABLE", "任务尚未终止或不存在")
            targets = [t for t, r in zip(job["targets"], job["items"]) if r["status"] in ("failed", "pending")]
            model_id, threshold = job["model_id"], job["threshold"]
        for t in targets:
            dataset, _ = self.registry.readable(t["cube_id"], raw=False)
            if source_signature(dataset) != t["signature"]:
                raise ModelingError("SOURCE_CHANGED", "原任务输入已变化，请重新明确范围")
            current = {k: file_sha256(Path(p)) for k, p in (("header", dataset.header_path), ("data", dataset.data_path))}
            if current != t["source_hashes"]:
                raise ModelingError("SOURCE_CHANGED", "原任务输入内容已变化，请重新明确范围")
        # A retry is explicit; remove only matching terminal idempotency entries.
        with self.lock:
            self.keys = {k: v for k, v in self.keys.items() if v != identifier}
        return self.submit(model_id, [t["cube_id"] for t in targets], threshold)

    def single(self, model, target, threshold, block_rows=32):
        cube_id, pack = target["cube_id"], model["calibration"]
        dataset, _ = self.registry.readable(cube_id, raw=False)
        if source_signature(dataset) != target["signature"]:
            raise ModelingError("SOURCE_CHANGED", "排队后输入已变化")
        hashes = {k: file_sha256(Path(p)) for k, p in (("header", dataset.header_path), ("data", dataset.data_path))}
        if target.get("source_hashes", hashes) != hashes:
            raise ModelingError("SOURCE_CHANGED", "排队后输入内容已变化")
        h, w, bands = dataset.shape
        identifier = str(uuid4())
        folder = self.paths.root / "inferences" / identifier
        storage.mkdir(folder, parents=True)
        arrays = []
        try:
            for name, dtype in (("labels", np.int32), ("argmax", np.int32), ("confidence", np.float32), ("state", np.uint8)):
                arrays.append(np.lib.format.open_memmap(storage.resolve_write(folder/(name + ".npy"), kind="ARTIFACT_WRITE"),
                                                       mode="w+", dtype=dtype, shape=(h, w)))
            label_map, raw_map, confidence_map, states = arrays
            counts = np.zeros(len(pack["classes"]), dtype=np.int64)
            valid_total = accepted_total = rejected_total = domain_total = 0
            histogram = np.zeros(20, np.int64)
            domain_accepted = domain_rejected = 0
            for first in range(0, h, block_rows):
                last = min(h, first+block_rows)
                raw = dataset.read_region(first, last, 0, w).reshape(-1, bands)
                valid = np.isfinite(raw).all(axis=1)
                labels = np.full(len(raw), -3, np.int32)
                raw_labels = labels.copy()
                confidence = np.zeros(len(raw), np.float32)
                state = np.zeros(len(raw), np.uint8)
                if valid.any():
                    transformed = apply_with_calibration(pack["calibration"], pack["pipeline"], raw[valid])
                    probs = predict(transformed[:, pack["columns"]], pack["model"])
                    pred = probs.argmax(axis=1).astype(np.int32)
                    raw_labels[valid] = pred
                    conf = probs.max(axis=1)
                    rejected = conf < threshold
                    pred[rejected] = -2
                    labels[valid], confidence[valid] = pred, conf
                    out = ((raw[valid] < np.asarray(pack["feature_min"])) | (raw[valid] > np.asarray(pack["feature_max"]))).any(axis=1)
                    state[valid] = np.where(out, 3, np.where(rejected, 2, 1))
                    counts += np.bincount(pred[pred >= 0], minlength=len(counts))
                    valid_total += len(pred); rejected_total += int(rejected.sum())
                    accepted_total += int((~rejected).sum()); domain_total += int(out.sum())
                    domain_accepted += int((out & ~rejected).sum()); domain_rejected += int((out & rejected).sum())
                    histogram += np.histogram(conf, bins=np.linspace(0, 1, 21))[0]
                label_map[first:last] = labels.reshape(last-first, w)
                raw_map[first:last] = raw_labels.reshape(last-first, w)
                confidence_map[first:last] = confidence.reshape(last-first, w)
                states[first:last] = state.reshape(last-first, w)
            for a in arrays:
                a.flush()
            for a in arrays:
                a._mmap.close()
            arrays.clear()
            if hashes != {k: file_sha256(Path(p)) for k, p in (("header", dataset.header_path), ("data", dataset.data_path))}:
                raise ModelingError("SOURCE_CHANGED", "推理期间源文件变化")
            stats = {"total_pixels": h*w, "valid_pixels": valid_total, "invalid_pixels": h*w-valid_total,
                     "accepted": accepted_total, "rejected": rejected_total, "out_of_domain": domain_total,
                     "out_of_domain_accepted": domain_accepted, "out_of_domain_rejected": domain_rejected,
                     "state_definition": "invalid/valid互斥；valid=accepted+rejected；out_of_domain是valid的交叉标志，不与前者相加",
                     "score_histogram": {"edges": np.linspace(0, 1, 21).tolist(), "counts": histogram.tolist()},
                     "coverage": accepted_total/valid_total if valid_total else None,
                     "classes": [{"label": i, "id": c["id"], "name": c["name"], "count": int(counts[i]),
                                  "fraction_accepted": int(counts[i])/accepted_total if accepted_total else None}
                                 for i, c in enumerate(pack["classes"])]}
            manifest = {"id": identifier, "model_id": model["id"], "model_version": model["version"], "model_hash": model["model_hash"],
                        "cube_id": cube_id, "shape": [h, w], "source_hashes": hashes, "threshold": threshold,
                        "stats": stats, "folder": identifier,
                        "files": {name: Evaluations.file_hash(folder/(name+".npy")) for name in ("labels", "argmax", "confidence", "state")},
                        "truth_available": False, "score_definition": "uncalibrated_softmax"}
            with connect_database(self.database) as db:
                db.execute("INSERT INTO classification_prediction VALUES (?,?,?,?,?)",
                           (identifier, model["id"], cube_id, encode(manifest), stamp()))
            return {"prediction_id": identifier, "stats": stats}
        except BaseException:
            for a in arrays:
                a._mmap.close()
            for name in ("labels", "argmax", "confidence", "state"):
                storage.unlink(folder/(name+".npy"), missing_ok=True)
            raise

    def manifest(self, identifier):
        import json
        with connect_database(self.database) as db:
            row = db.execute("SELECT manifest FROM classification_prediction WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise ModelingError("PREDICTION_NOT_FOUND", "分类推理产物不存在")
        return json.loads(row[0])

    def evaluate(self, identifier, annotation_version_id):
        """A distinct frozen-truth evaluation; prediction receipts remain truth-free."""
        import json
        from pathlib import PurePosixPath
        from .evaluation import summarize, NAMES
        manifest = self.manifest(identifier)
        model = self.models.get(manifest["model_id"])
        store = self.models.store
        original = store.get(model["evaluation_id"])
        with connect_database(self.database) as db:
            row = db.execute("SELECT cube_id,snapshot_ref FROM annotation_version WHERE id=?", (annotation_version_id,)).fetchone()
        if not row or row[0] != manifest["cube_id"]:
            raise ModelingError("TRUTH_MISMATCH", "真值版本与推理图像不匹配")
        dataset, _ = self.registry.readable(manifest["cube_id"], raw=False)
        current = {k: file_sha256(Path(p)) for k, p in (("header", dataset.header_path), ("data", dataset.data_path))}
        if current != manifest["source_hashes"]:
            raise ModelingError("SOURCE_CHANGED", "当前源数据与推理时内容不一致")
        relative = PurePosixPath(row[1])
        root = self.paths.snapshots.resolve()
        truth_folder = root.joinpath(*relative.parts).resolve()
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative) or ":" in str(relative) or not truth_folder.is_relative_to(root):
            raise ModelingError("INVALID_SNAPSHOT_REF", "真值快照路径非法")
        hashes = {name: file_sha256(truth_folder/name) for name in ("label_map.npz", "label_index.json")}
        with np.load(truth_folder/"label_map.npz", allow_pickle=False) as archive:
            labels = archive["label_map"].copy()
        mapping = json.loads((truth_folder/"label_index.json").read_text("utf-8"))
        if labels.shape != tuple(manifest["shape"]) or labels.dtype.kind not in "iu":
            raise ModelingError("TRUTH_MISMATCH", "真值坐标或编码不匹配")
        catalog = {c["id"]: c["label"] for c in original["classes"]}
        truth = np.full(labels.shape, -1, np.int32)
        for local in np.unique(labels[labels >= 0]):
            identity = mapping.get(str(int(local)))
            if identity not in catalog:
                raise ModelingError("TRUTH_CLASS_MISMATCH", "真值含冻结分类目录之外的类别")
            truth[labels == local] = catalog[identity]
        folder = self.paths.root / "inferences" / identifier
        arrays = {}
        try:
            for name in ("argmax", "confidence"):
                path = folder/(name+".npy")
                if name not in manifest["files"] or Evaluations.file_hash(path) != manifest["files"][name]:
                    raise ModelingError("ARTIFACT_HASH_MISMATCH", "评价所需推理产物缺失或损坏")
                arrays[name] = np.load(path, mmap_mode="r", allow_pickle=False)
            valid = (truth >= 0) & (arrays["argmax"] >= 0)
            positions = np.flatnonzero(valid.ravel())
            if not len(positions):
                raise ModelingError("NO_VALID_TRUTH", "真值范围与有效预测没有交集")
            y, pred, conf = truth[valid], np.asarray(arrays["argmax"][valid]), np.asarray(arrays["confidence"][valid])
            groups = np.zeros(len(y), np.int32)
            report = summarize(y, pred, groups, conf, groups, labels=list(range(len(catalog))), threshold=manifest["threshold"])
            for population in report["populations"].values():
                population["folds"] = []
                population["fold_summary"] = {scope: {name: {"mean": None, "std": None, "n_effective": 0} for name in NAMES}
                                              for scope in ("pixel", "sample")}
            if hashes != {name: file_sha256(truth_folder/name) for name in hashes}:
                raise ModelingError("TRUTH_CHANGED", "评价时真值快照变化")
            cube = {"cube_id": manifest["cube_id"], "name": dataset.name, "shape": list(dataset.shape), "group": 0,
                    "annotation_version_id": annotation_version_id, "source_hashes": current,
                    "snapshot_hash": hashes["label_map.npz"], "label_index_hash": hashes["label_index.json"]}
            evaluation = {"protocol": "independent_inference", "operator": "evaluate_classification_inference", "operator_version": 1,
                          "classes": original["classes"], "cubes": [cube], "group_kind": "cube_proxy", "n_images": 1, "n_groups": 1,
                          "n_pixels": len(y), "prediction_id": identifier, "model_id": model["id"], "model_version": model["version"],
                          "source_evaluation_id": model["evaluation_id"], "input_identity": {"prediction": identifier, "truth": hashes},
                          "limitations": ["独立真值评价，不是交叉验证；没有折均值和折SD。",
                              "若真值来自训练成员，本评价不构成独立泛化证据。", "真值留白、无效谱不参与评价；图像多数投票仅描述主类。"], **report}
            return store.create(model["run_id"], evaluation, arrays={"observations": {"y": y, "raw_pred": pred,
                "confidence": conf, "groups": groups, "flat_index": positions, "cube_index": groups}})
        finally:
            for array in arrays.values():
                array._mmap.close()

    def prediction_tile(self, identifier, *, level=0, tile_x=0, tile_y=0, layer="prediction", size=256, hidden=None, colors=None):
        if layer not in ("prediction", "confidence", "rejected"):
            raise ModelingError("TRUTH_UNAVAILABLE", "新数据未提供匹配真值，不能生成真值或误分图层")
        import json
        with connect_database(self.database) as db:
            row = db.execute("SELECT manifest FROM classification_prediction WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise ModelingError("PREDICTION_NOT_FOUND", "分类推理产物不存在")
        manifest = json.loads(row[0])
        model = self.models.get(manifest["model_id"])
        scale = 2**level
        h, w = manifest["shape"]
        x0, y0 = tile_x*size*scale, tile_y*size*scale
        if not 0 <= x0 < w or not 0 <= y0 < h:
            raise ModelingError("TILE_OUT_OF_BOUNDS", "推理瓦片超出图像")
        from uuid import UUID
        if str(UUID(manifest["folder"])) != manifest["folder"]:
            raise ModelingError("INVALID_ARTIFACT", "推理目录身份非法")
        folder = self.paths.root / "inferences" / manifest["folder"]
        arrays = {}
        try:
            for name in ("labels", "confidence", "state"):
                path = folder/(name+".npy")
                if Evaluations.file_hash(path) != manifest["files"][name]:
                    raise ModelingError("ARTIFACT_HASH_MISMATCH", "推理产物已损坏")
                arrays[name] = np.load(path, mmap_mode="r", allow_pickle=False)
            labels = arrays["labels"][y0:min(h, y0+size*scale):scale, x0:min(w, x0+size*scale):scale]
            rgb = np.full((*labels.shape, 3), [35, 45, 54], dtype=np.uint8)
            for c in model["classes"]:
                if c["label"] in (hidden or []):
                    continue
                color = (colors or {}).get(str(c["label"]), c["color"])
                rgb[labels == c["label"]] = [int(color[j:j+2], 16) for j in (1, 3, 5)]
            rgb[labels == -2] = [220, 170, 40]
            if layer == "confidence":
                v = arrays["confidence"][y0:min(h,y0+size*scale):scale,x0:min(w,x0+size*scale):scale]
                rgb = np.stack([255-v*255, v*255, np.full_like(v, 120)], axis=2).astype(np.uint8)
            elif layer == "rejected":
                rgb[:] = [75, 95, 95]
                rgb[labels == -2] = [220, 170, 40]
            rgb[labels == -3] = [35, 45, 54]
            return {"prediction_id": identifier, "width": labels.shape[1], "height": labels.shape[0],
                    "original_width": w, "original_height": h, "level": level, "tile_x": tile_x, "tile_y": tile_y,
                    "png_base64": png_rgb(rgb), "mime": "image/png",
                    "legend": model["classes"], "stats": manifest["stats"], "truth_available": False,
                    "limitation": "无真值，只报告预测分布；分类得分未校准；物理尺度未知，比例尺px。"}
        finally:
            for a in arrays.values():
                a._mmap.close()
