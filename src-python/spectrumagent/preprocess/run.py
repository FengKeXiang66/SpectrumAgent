"""R12 synchronous run: preflight, bounded raw reads, global fits, two artifacts."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
from uuid import uuid4

import numpy as np

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.annotation.engines.superpixels import memory_bytes
from spectrumagent.data.readers.binary import json_object
from spectrumagent.data.readers.header import classic, read_text
from . import builtin_registry
from .compare import PixelMetrics, ranking
from .operators.ica import fit_ica
from .operators.mnf import fit_mnf
from .operators.pca import fit_pca, transform
from .operators.ica import ica
from .operators.mnf import mnf
from .operators.pca import pca
from .operators.standardize import standardize
from .recipes import RecipeStore, input_fingerprint
from .registry import OperatorRegistry, PreprocessError, invalid, json_safe


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def peak_rss():
    return memory_bytes()[1]


def remove_directory(path, root):
    resolved, boundary = path.resolve(), root.resolve()
    if resolved == boundary or not resolved.is_relative_to(boundary):
        raise ValueError("拒绝清理输出根以外的目录")
    if resolved.exists():
        shutil.rmtree(resolved)


def file_sha256(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _error(code, detail, **context):
    error = PreprocessError(code, detail, **context)
    error.status_code = 404
    return error


@dataclass
class BoundedInput:
    registry: object
    cube_id: str
    shape: tuple
    label_map: np.ndarray
    block_size: int
    hdr: dict
    branch: str
    guard: str
    operators: OperatorRegistry

    def lines(self):
        labeled = bool(np.any(self.label_map >= 0))
        for l0 in range(0, self.shape[0], self.block_size):
            dataset, _ = self.registry.readable(self.cube_id, raw=True)
            block = dataset.read_region(l0, min(l0+self.block_size, self.shape[0]), 0, self.shape[1])
            for offset, line in enumerate(block):
                indices = self.label_map[l0+offset]
                selected = indices >= 0 if labeled else indices == -1
                if not selected.any():
                    continue
                # B01 is reapplied to raw DN for every pass, never to reflectance.
                converted = self.operators.run(line[selected], {"steps": [{"op": "reflectance", "version": 1,
                    "params": {"hdr": self.hdr, "branch": self.branch, "guard": self.guard}}]})
                yield converted.spectra, indices[selected], converted.steps[0]
            del block, dataset, line


def fit_standard(factory, params):
    total = squares = low = high = None
    count = 0
    for block in factory():
        if total is None:
            total, squares = np.zeros(block.shape[1]), np.zeros(block.shape[1])
            low, high = np.full(block.shape[1], np.inf), np.full(block.shape[1], -np.inf)
        total += block.sum(axis=0)
        squares += (block*block).sum(axis=0)
        low, high = np.minimum(low, block.min(axis=0)), np.maximum(high, block.max(axis=0))
        count += len(block)
    if not count:
        raise invalid("spectra", "没有可拟合像素")
    if params["method"] == "standard":
        offset = total/count
        scale = np.sqrt(np.maximum(squares/count-offset*offset, 0.))
        scale[low == high] = 0.  # Exact constant bands must obey zero_std, not cancellation noise.
        fitted = [{"mean": float(a), "std": float(b)} for a, b in zip(offset, scale)]
    else:
        offset, scale = low, high-low
        fitted = [{"min": float(a), "max": float(b)} for a, b in zip(low, high)]
    zero = scale == 0
    zero_count = int(zero.sum())
    if zero_count and params["zero_std"] == "error":
        raise PreprocessError("NORMALIZATION_DEGENERATE", "归一化分母为零", zero_scale_count=zero_count)
    def apply(x):
        with np.errstate(divide="ignore", invalid="ignore"):
            result = (x-offset)/scale
        if zero_count:
            result[:, zero] = 0. if params["zero_std"] == "zeros" else np.nan
        return result
    return apply, {"method": params["method"], "fitted": fitted,
                   "n_spectra": count, "zero_scale_count": zero_count}


class RunEngine:
    def __init__(self, registry, paths, operators=None):
        self.registry, self.paths = registry, paths
        self.database = registry.database
        self.operators = operators if operators is not None else builtin_registry()
        self.recipes = RecipeStore(self.database, self.operators)

    def _preflight(self, cube_id, annotation_version_id, recipe_version_id, block_size, guard):
        if type(block_size) is not int or block_size < 1:
            raise invalid("block_size", "block_size 须为正整数")
        dataset, _ = self.registry.readable(cube_id, raw=True)
        files = {Path(dataset.header_path), Path(dataset.data_path)}
        root = Path(os.path.commonpath([str(path.parent) for path in files]))
        try:
            hashes = {path.relative_to(root).as_posix(): file_sha256(path) for path in sorted(files)}
        except OSError as error:
            raise PreprocessError("SOURCE_CHANGED", "源哈希读取失败", reason=str(error)) from error
        with connect_database(self.database) as db:
            annotation = db.execute("SELECT cube_id,snapshot_ref FROM annotation_version WHERE id=?",
                                    (str(annotation_version_id),)).fetchone()
            if annotation is None or annotation[0] != str(cube_id):
                raise _error("VERSION_NOT_FOUND", "标注版本不存在或不属于该 cube", version_id=str(annotation_version_id))
            recipe = db.execute("SELECT pipeline FROM preprocess_recipe_version WHERE id=?", (str(recipe_version_id),)).fetchone()
            if recipe is None:
                raise _error("RECIPE_VERSION_NOT_FOUND", "配方版本不存在", recipe_version_id=str(recipe_version_id))
        pipeline = self.operators.parse_pipeline(recipe[0])
        if any(step.op == "reflectance" for step in pipeline.steps):
            raise invalid("pipeline", "反射率转换由 run 前置，不得在配方中重复施加")
        relative = PurePosixPath(annotation[1])
        if relative.is_absolute() or ".." in relative.parts or "\\" in annotation[1] or ":" in annotation[1]:
            raise PreprocessError("INVALID_SNAPSHOT_REF", "快照须为 POSIX 相对路径")
        directory = self.paths.snapshots.joinpath(*relative.parts)
        try:
            with np.load(directory/"label_map.npz", allow_pickle=False) as archive:
                label_map = archive["label_map"].copy()
            label_index = json.loads((directory/"label_index.json").read_text("utf-8"))
        except (OSError, ValueError, KeyError) as error:
            raise PreprocessError("INVALID_SNAPSHOT_REF", "无法读取标注快照", reason=str(error)) from error
        if label_map.shape != dataset.shape[:2] or label_map.dtype != np.int32 or np.any(label_map < -2):
            raise PreprocessError("INVALID_SNAPSHOT_REF", "label_map 与 cube 轴序或三态编码不匹配")
        if any(str(index) not in label_index for index in np.unique(label_map[label_map >= 0])):
            raise PreprocessError("INVALID_SNAPSHOT_REF", "label_index 缺少已标像素映射")
        text = read_text(dataset.header_path)
        hdr = json_object(text) if text.lstrip().startswith("{") else classic(text, magic=text.lstrip().startswith("ENVI"))
        first = dataset.read_region(0, min(block_size, dataset.shape[0]), 0, dataset.shape[1])
        branch = self.operators.run(first.reshape(-1, dataset.shape[2]), {"steps": [{"op": "reflectance", "version": 1,
            "params": {"hdr": hdr, "guard": guard}}]}).steps[0]["meta"]["branch"]
        del first
        count = int((label_map >= 0).sum()) if np.any(label_map >= 0) else int((label_map == -1).sum())
        if not count:
            raise invalid("annotation_version_id", "没有可处理像素；不确定像素不参与拟合")
        fingerprint = input_fingerprint(str(cube_id), hashes, str(annotation_version_id), count)
        source = BoundedInput(self.registry, str(cube_id), dataset.shape, label_map, block_size, hdr, branch, guard, self.operators)
        return dataset, source, pipeline, label_index, hashes, fingerprint

    def _step(self, x, axis, step, fitted):
        registry = self.operators
        if fitted is not None:
            registry = OperatorRegistry()
            entry = self.operators.resolve(step.op, step.version)
            apply, meta = fitted
            registry.register(step.op, step.version, entry.model, lambda data, params: (apply(data), meta))
        return registry.run(x, {"steps": [step.model_dump()]}, wavelengths=axis)

    def _stream(self, source, steps, fits, wavelengths):
        for x, indices, b01 in source.lines():
            axis, records = wavelengths, []
            for position, step in enumerate(steps):
                result = self._step(x, axis, step, fits.get(position))
                x, axis = result.spectra, result.wavelengths
                records.extend(result.steps)
            yield x, indices, axis, records, b01

    def _transition(self, identifier, status, **values):
        allowed = {"finished_at", "error", "metrics", "scaler_params"}
        if set(values)-allowed:
            raise ValueError("invalid run columns")
        with connect_database(self.database) as db:
            fields = ["status=?", *[f"{key}=?" for key in values]]
            db.execute(f"UPDATE preprocess_run SET {','.join(fields)} WHERE id=?", (status, *values.values(), identifier))

    @staticmethod
    def _merge_records(records, incoming, fits):
        for i, record in enumerate(incoming):
            if i in fits:
                continue  # Calibrated step metadata already describes the full input.
            current, extra = records[i]["meta"], record["meta"]
            for key in ("negative_clipped", "nan_bands", "zero_std_count", "zero_scale_count",
                        "nan_spectra", "zero_continuum_bands", "n_spectra"):
                if key in extra:
                    current[key] += extra[key]
            if "hull_vertex_counts" in extra:
                current["hull_vertex_counts"].extend(extra["hull_vertex_counts"])
            if "coefficients_sha256" in extra:
                current["coefficients_scope"] = "logical_line; coefficient_blocks records every line"
                current.setdefault("coefficient_blocks", [{"shape": current["coefficients_shape"],
                    "sha256": current["coefficients_sha256"]}]).append({"shape": extra["coefficients_shape"],
                                                                      "sha256": extra["coefficients_sha256"]})

    def run(self, cube_id, annotation_version_id, recipe_version_id, *, block_size=32, guard="clip", note=None):
        dataset, source, pipeline, label_index, hashes, fingerprint = self._preflight(
            cube_id, annotation_version_id, recipe_version_id, block_size, guard)
        wavelengths = np.asarray(dataset.wavelengths) if dataset.wavelengths else None
        del dataset  # Release the preflight reader/mapping before bounded passes.
        identifier = str(uuid4())
        with connect_database(self.database) as db:
            previous = db.execute("SELECT input_fingerprint FROM preprocess_run WHERE cube_id=? AND recipe_version_id=? "
                                  "AND status='succeeded' ORDER BY created_at DESC LIMIT 1", (str(cube_id), str(recipe_version_id))).fetchone()
            db.execute("INSERT INTO preprocess_run (id,cube_id,annotation_version_id,recipe_version_id,b01_branch,"
                       "input_fingerprint,status,note,created_at) VALUES (?,?,?,?,?,?,'pending',?,?)",
                       (identifier, str(cube_id), str(annotation_version_id), str(recipe_version_id), source.branch, fingerprint, note, timestamp()))
        directory = self.paths.preprocessed / str(cube_id) / identifier
        temporary = directory / ".tmp"
        temp_bytes, temp_peak_bytes, rss = 0, 0, peak_rss()
        try:
            self._transition(identifier, "running")
            directory.mkdir(parents=True, exist_ok=False)
            fits = {}
            for i, step in enumerate(pipeline.steps):
                entry = self.operators.resolve(step.op, step.version)
                params = entry.model.model_validate(step.params).model_dump()
                factory = lambda i=i: (item[0] for item in self._stream(source, pipeline.steps[:i], fits, wavelengths))
                if entry.impl is standardize and params["method"] in ("standard", "minmax"):
                    fits[i] = fit_standard(factory, params)
                elif entry.impl in (pca, mnf):
                    mean, loadings, meta = (fit_pca if entry.impl is pca else fit_mnf)(factory, params)
                    fits[i] = (lambda x, mean=mean, loadings=loadings: transform(x, mean, loadings), meta)
                elif entry.impl is ica:
                    count = invalid_count = 0
                    bands = None
                    for block in factory():
                        valid = np.isfinite(block).all(axis=1)
                        count += int(valid.sum())
                        invalid_count += int((~valid).sum())
                        bands = block.shape[1]
                    if not count:
                        raise PreprocessError("DECOMPOSITION_DEGENERATE", "ICA 没有有限谱")
                    temporary.mkdir(exist_ok=True)
                    path = temporary / f"ica-{i}.dat"
                    mapped = np.memmap(path, dtype=np.float64, mode="w+", shape=(count, bands))
                    try:
                        offset = 0
                        for block in factory():
                            finite = block[np.isfinite(block).all(axis=1)]
                            mapped[offset:offset+len(finite)] = finite
                            offset += len(finite)
                        mapped.flush()
                        temp_bytes += mapped.nbytes
                        temp_peak_bytes = max(temp_peak_bytes, mapped.nbytes)
                        mean, loadings, meta = fit_ica(mapped, params, nan_count=invalid_count)
                        rss = max(rss, peak_rss())
                    finally:
                        mapped._mmap.close()
                        path.unlink(missing_ok=True)
                    fits[i] = (lambda x, mean=mean, loadings=loadings: transform(x, mean, loadings), meta)
            metrics = PixelMetrics()
            records, b01_meta, final_axis = [], None, wavelengths
            for x, indices, final_axis, line_records, b01 in self._stream(source, pipeline.steps, fits, wavelengths):
                metrics.update(x, indices)
                if not records:
                    records = line_records
                else:
                    self._merge_records(records, line_records, fits)
                if b01_meta is None:
                    b01_meta = b01
                else:
                    for key in ("negative_clipped", "nan_bands"):
                        b01_meta["meta"][key] += b01["meta"][key]
            measured, moments = metrics.result(labeled=bool(np.any(source.label_map >= 0)))
            scaler = [entry[1]["fitted"] for i, entry in sorted(fits.items()) if pipeline.steps[i].op == "standardize"]
            # Area/vector have no global fit but still supply their explicit [] fitted.
            scaler_records = [record["meta"]["fitted"] for record in records if record["op"] == "standardize"]
            scaler = scaler_records if scaler_records else scaler
            scaler_value = scaler[0] if len(scaler) == 1 else scaler if scaler else None
            report = {"run_id": identifier, "cube_id": str(cube_id), "annotation_version_id": str(annotation_version_id),
                      "recipe_version_id": str(recipe_version_id), "input_fingerprint": fingerprint,
                      "source_hashes": hashes, "label_index": label_index, "metrics": measured, "steps": records,
                      "b01": b01_meta, "wavelengths": final_axis, "temporary_bytes": temp_bytes,
                      "temporary_peak_bytes": temp_peak_bytes,
                      "temporary_data": "ICA 当前输入（选中像素→B01→前序步骤）的有限行；float64 单份 memmap；temporary_bytes 为累计写入字节",
                      "peak_rss_bytes": max(rss, peak_rss()), "input_fingerprint_matches_previous":
                      None if previous is None else previous[0] == fingerprint,
                      "fitting_source": {"dataset_id": str(cube_id), "input_fingerprint": fingerprint,
                                         "n_spectra": int((source.label_map >= 0).sum()) if np.any(source.label_map >= 0) else int((source.label_map == -1).sum())},
                      "not_applicable": ["processed_cube/overlay：阶段一不产出；未登记临时 ICA 文件。"]}
            row = {"id": identifier, "recipe_version_id": str(recipe_version_id), "status": "succeeded", "metrics": measured}
            report["ranking"] = ranking([row])
            arrays = {f"{kind}_{index}": value[kind].astype(np.float64) for index, value in moments.items() for kind in ("mean", "std")}
            with (directory/"sample_spectra.npz.tmp").open("wb") as stream:
                np.savez_compressed(stream, **arrays)
            (directory/"report.json.tmp").write_text(json.dumps(json_safe(report), ensure_ascii=False, allow_nan=False), "utf-8")
            artifacts = []
            for kind, filename in (("sample_spectra", "sample_spectra.npz"), ("report", "report.json")):
                target = directory/filename
                os.replace(directory/(filename+".tmp"), target)
                artifacts.append((str(uuid4()), identifier, kind, target.relative_to(self.paths.preprocessed).as_posix(), file_sha256(target), timestamp()))
            with connect_database(self.database) as db:
                db.executemany("INSERT INTO preprocess_artifact (id,run_id,kind,relative_path,sha256,created_at) VALUES (?,?,?,?,?,?)", artifacts)
                db.execute("UPDATE preprocess_run SET status='succeeded',metrics=?,scaler_params=?,finished_at=? WHERE id=?",
                           (json.dumps(measured, ensure_ascii=False, allow_nan=False), None if scaler_value is None else json.dumps(json_safe(scaler_value), allow_nan=False), timestamp(), identifier))
        except Exception as error:
            structured = error if isinstance(error, DataError) else PreprocessError("PREPROCESS_RUN_FAILED", "预处理执行失败", reason=str(error))
            if directory.exists():
                remove_directory(directory, self.paths.preprocessed)
            self._transition(identifier, "failed", error=json.dumps(structured.as_dict(), ensure_ascii=False), finished_at=timestamp())
        finally:
            if temporary.exists():
                remove_directory(temporary, self.paths.preprocessed)
        return self.get(identifier)

    def get(self, identifier):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM preprocess_run WHERE id=?", (str(identifier),)).fetchone()
            if row is None:
                raise _error("RUN_NOT_FOUND", "run 不存在", run_id=str(identifier))
            result = dict(row)
            result["artifacts"] = [dict(item) for item in db.execute("SELECT * FROM preprocess_artifact WHERE run_id=? ORDER BY kind", (str(identifier),))]
        for key in ("metrics", "scaler_params", "error"):
            if result[key] is not None:
                result[key] = json.loads(result[key])
        return result
