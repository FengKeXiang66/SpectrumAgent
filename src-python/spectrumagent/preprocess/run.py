"""R12 synchronous run: preflight, bounded raw reads, global fits, two artifacts."""
from spectrumagent.storage import guard as storage
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import sys
from time import perf_counter
from uuid import UUID, uuid4

import numpy as np

from backend.database import connect_database
from spectrumagent import projects
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
from . import submissions


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def peak_rss():
    return memory_bytes()[1]


def code_version():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).resolve().parent,
                              capture_output=True, text=True, check=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def remove_directory(path, root):
    resolved, boundary = path.resolve(), root.resolve()
    if resolved == boundary or not resolved.is_relative_to(boundary):
        raise ValueError("拒绝清理输出根以外的目录")
    if resolved.exists():
        storage.rmtree(resolved)


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
    collect_before: bool = False
    before: dict = field(default_factory=dict)

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
                if self.collect_before:
                    for index in np.unique(indices[selected]):
                        pixels = converted.spectra[indices[selected] == index]
                        state = self.before.setdefault(int(index), {"count": 0, "sum": np.zeros(pixels.shape[1])})
                        state["count"] += len(pixels)
                        state["sum"] += pixels.sum(axis=0)
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
        from .current import initialize
        initialize(self.database)
        self.executor_id = str(uuid4())
        from .drafts import RecipeDrafts
        self.drafts = RecipeDrafts(self.recipes,self)

    def _preflight(self, cube_id, annotation_version_id, recipe_version_id, block_size, guard):
        with connect_database(self.database) as db:
            for kind, reference in [('cube', cube_id), ('annotation', annotation_version_id), ('recipe_version', recipe_version_id)]:
                projects.require(db, kind, reference)
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
            from .current import input_identity
            if input_identity(db, annotation_version_id, recipe_version_id) is None:
                raise PreprocessError('CURRENT_INPUT_REQUIRED', '请使用当前已保存的标注和配方')
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
        # A mutable annotation ID no longer identifies its content.
        from .recipes import annotation_identity
        annotation_digest = annotation_identity(label_map, label_index)
        fingerprint = input_fingerprint(str(cube_id), hashes, str(annotation_version_id)+":"+annotation_digest, count)
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
        import sklearn

        started = perf_counter()
        submission = submissions.context()
        payload = dict(cube_id=str(cube_id), annotation_version_id=str(annotation_version_id),
                       recipe_version_id=str(recipe_version_id), block_size=block_size, guard=guard, note=note)
        with connect_database(self.database) as db:
            from .current import input_identity
            payload['current_input_identity'] = input_identity(db, annotation_version_id, recipe_version_id)
            old = submissions.lookup(db, submission, 'preprocess.run', payload)
        if old is not None:
            return self.get(old['run_id'])
        from .drafts import assert_available, assert_confirmation
        member={key:payload[key] for key in ('cube_id','annotation_version_id','recipe_version_id')}
        with connect_database(self.database) as db:
            if not submissions.admitted(submission,member):
                assert_available(db,version_id=recipe_version_id)
        dataset, source, pipeline, label_index, hashes, fingerprint = self._preflight(
            cube_id, annotation_version_id, recipe_version_id, block_size, guard)
        wavelengths = np.asarray(dataset.wavelengths) if dataset.wavelengths else None
        del dataset  # Release the preflight reader/mapping before bounded passes.
        identifier = str(uuid4())
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            operation, fresh = submissions.begin(db, submission, 'preprocess.run', payload, run_id=identifier)
            if not fresh:
                return self.get(operation['run_id'])
            if not submissions.admitted(submission,member):
                assert_available(db,version_id=recipe_version_id)
            assert_confirmation(db,submission,member,fingerprint)
            recipe_hash_alg, recipe_pipeline_sha256 = db.execute(
                "SELECT algorithm,sha256 FROM recipe_pipeline_hash WHERE recipe_version_id=?",
                (str(recipe_version_id),)).fetchone()
            previous = db.execute("SELECT input_fingerprint FROM preprocess_run WHERE cube_id=? AND recipe_version_id=? "
                                  "AND status='succeeded' ORDER BY created_at DESC LIMIT 1", (str(cube_id), str(recipe_version_id))).fetchone()
            project_id = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (str(cube_id),)).fetchone()[0]
            db.execute("INSERT INTO preprocess_run (id,cube_id,annotation_version_id,recipe_version_id,b01_branch,"
                       "input_fingerprint,status,note,created_at) VALUES (?,?,?,?,?,?,'pending',?,?)",
                       (identifier, str(cube_id), str(annotation_version_id), str(recipe_version_id), source.branch, fingerprint, note, timestamp()))
            from .current import input_identity
            identity = input_identity(db, annotation_version_id, recipe_version_id)
            if identity:
                db.execute('INSERT INTO current_run_input VALUES (?,?,?)', (identifier,*identity))
            root = self.paths.artifact_root
            directory = self.paths.preprocess_directory(project_id, cube_id, identifier)
            db.execute('UPDATE business_operation SET evidence_root=?,evidence_directory=? WHERE operation_id=?',
                       (str(root), directory.relative_to(root).as_posix(), operation['operation_id']))
        if not submissions.claim(self.database, operation['operation_id'], self.executor_id):
            return self.get(identifier)
        temporary = directory / ".tmp"
        temp_bytes, temp_peak_bytes, rss = 0, 0, peak_rss()
        publishing = False
        try:
            self._transition(identifier, "running")
            storage.mkdir(directory, parents=True, exist_ok=False)
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
                    storage.mkdir(temporary, exist_ok=True)
                    path = temporary / f"ica-{i}.dat"
                    mapped = np.memmap(storage.resolve_write(path, kind="ARTIFACT_WRITE"), dtype=np.float64, mode="w+", shape=(count, bands))
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
                        try:
                            mapped._mmap.close()
                        except Exception:
                            pass
                        try:
                            storage.unlink(path, missing_ok=True)
                        except Exception:
                            pass  # Scratch cleanup must not replace the fitting error.
                    fits[i] = (lambda x, mean=mean, loadings=loadings: transform(x, mean, loadings), meta)
            metrics = PixelMetrics()
            unlabeled_after = {"count": 0, "sum": None}
            records, b01_meta, final_axis = [], None, wavelengths
            source.collect_before = True  # Fits above may reread lines; collect only the final execution pass.
            for x, indices, final_axis, line_records, b01 in self._stream(source, pipeline.steps, fits, wavelengths):
                metrics.update(x, indices)
                if np.all(indices == -1):
                    finite = x[np.isfinite(x).all(axis=1)]
                    if len(finite):
                        if unlabeled_after["sum"] is None:
                            unlabeled_after["sum"] = np.zeros(x.shape[1])
                        unlabeled_after["sum"] += finite.sum(axis=0)
                        unlabeled_after["count"] += len(finite)
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
            in_index = np.unique(np.round(np.linspace(0, source.shape[2]-1, min(source.shape[2], 512))).astype(int))
            out_bands = x.shape[1]
            out_index = np.unique(np.round(np.linspace(0, out_bands-1, min(out_bands, 512))).astype(int))
            curve_after = {index: value["mean"] for index, value in moments.items()}
            if unlabeled_after["count"]:
                curve_after[-1] = unlabeled_after["sum"]/unlabeled_after["count"]
            curves = {"labeled": bool(np.any(source.label_map >= 0)),
                      "wavelengths_in": wavelengths[in_index] if wavelengths is not None and len(wavelengths) else None,
                      "wavelengths_out": final_axis[out_index] if final_axis is not None and len(final_axis) else None,
                      "classes": [{"label_index": index, "count": state["count"],
                                   "before": (state["sum"]/state["count"])[in_index],
                                   "after": curve_after[index][out_index] if index in curve_after else None}
                                  for index, state in sorted(source.before.items())],
                      "sampling": "等距索引 np.unique(round(linspace(0,n-1,min(n,512))))；确定性，非均值池化"}
            scaler = [entry[1]["fitted"] for i, entry in sorted(fits.items()) if pipeline.steps[i].op == "standardize"]
            # Area/vector have no global fit but still supply their explicit [] fitted.
            scaler_records = [record["meta"]["fitted"] for record in records if record["op"] == "standardize"]
            scaler = scaler_records if scaler_records else scaler
            scaler_value = scaler[0] if len(scaler) == 1 else scaler if scaler else None
            revision = code_version()
            report = {"run_id": identifier, "cube_id": str(cube_id), "annotation_version_id": str(annotation_version_id),
                      "recipe_version_id": str(recipe_version_id), "input_fingerprint": fingerprint,
                      "source_hashes": hashes, "label_index": label_index, "metrics": measured, "steps": records,
                      "b01": b01_meta, "wavelengths": final_axis, "curves": curves, "temporary_bytes": temp_bytes,
                      "temporary_peak_bytes": temp_peak_bytes,
                      "temporary_data": "ICA 当前输入（选中像素→B01→前序步骤）的有限行；float64 单份 memmap；temporary_bytes 为累计写入字节",
                      "peak_rss_bytes": max(rss, peak_rss()), "input_fingerprint_matches_previous":
                      None if previous is None else previous[0] == fingerprint,
                      "fitting_source": {"dataset_id": str(cube_id), "input_fingerprint": fingerprint,
                                         "n_spectra": int((source.label_map >= 0).sum()) if np.any(source.label_map >= 0) else int((source.label_map == -1).sum())},
                      "not_applicable": ["processed_cube/overlay：阶段一不产出；未登记临时 ICA 文件。"]}
            report.update(
                env={"python": sys.version, "numpy": np.__version__, "sklearn": sklearn.__version__},
                code_version=revision, image_digest=None, seed=None, operator=None, actor="local",
                seed_sources=[{"step_index": i, "op": record["op"], "version": record["version"],
                               "random_state": record["params"]["random_state"]}
                              for i, record in enumerate(records) if "random_state" in record["params"]],
                duration_s=perf_counter()-started,
                recipe_pipeline_sha256=recipe_pipeline_sha256, recipe_hash_alg=recipe_hash_alg,
                outputs={"artifacts": [{"kind": kind, "relative_path": (directory/filename).relative_to(root).as_posix()}
                                       for kind, filename in (("sample_spectra", "sample_spectra.npz"), ("report", "report.json"))]},
                reproducibility_assertion="同 recipe_pipeline_sha256 + 同 input_fingerprint + 同算子版本重跑：`sample_spectra.npz` 的 SHA256 必须一致；`report.json` 含 run_id / duration_s 等动态字段，不承诺文件字节一致，仅核验 `recipe_pipeline_sha256` / `input_fingerprint` / `metrics` / `steps` 语义一致")
            report["not_applicable"].extend([
                "image_digest：单机桌面无容器，不适用。", "seed：run 层无全局 seed；各 step 见 seed_sources。",
                "operator：单机单用户、进程即身份；actor 为 local，不记录人名。"])
            if revision is None:
                report["not_applicable"].append("code_version：无法取得 git HEAD。")
            row = {"id": identifier, "recipe_version_id": str(recipe_version_id), "status": "succeeded", "metrics": measured}
            report["ranking"] = ranking([row])
            arrays = {f"{kind}_{index}": value[kind].astype(np.float64) for index, value in moments.items() for kind in ("mean", "std")}
            with (storage.resolve_write(directory/"sample_spectra.npz.tmp", kind="FILE_OPEN")).open("wb") as stream:
                np.savez_compressed(stream, **arrays)
            (storage.resolve_write(directory/"report.json.tmp", kind="WRITE_TEXT")).write_text(json.dumps(json_safe(report), ensure_ascii=False, allow_nan=False), "utf-8")
            artifacts = []
            publishing = True  # Before the FIRST replace: even that call may partially publish.
            for kind, filename in (("sample_spectra", "sample_spectra.npz"), ("report", "report.json")):
                target = directory/filename
                storage.replace(directory/(filename+".tmp"), target)
                artifacts.append((str(uuid4()), identifier, kind, target.relative_to(root).as_posix(), file_sha256(target), timestamp()))
            with connect_database(self.database) as db:
                db.execute('BEGIN IMMEDIATE')
                db.executemany("INSERT INTO preprocess_artifact (id,run_id,kind,relative_path,sha256,created_at) VALUES (?,?,?,?,?,?)", artifacts)
                db.execute("UPDATE preprocess_run SET status='succeeded',metrics=?,scaler_params=?,finished_at=? WHERE id=?",
                           (json.dumps(measured, ensure_ascii=False, allow_nan=False), None if scaler_value is None else json.dumps(json_safe(scaler_value), allow_nan=False), timestamp(), identifier))
                submissions.finish(db, operation['operation_id'], 'succeeded', self._get(db, identifier))
        except Exception as error:
            structured = error if isinstance(error, DataError) else PreprocessError("PREPROCESS_RUN_FAILED", "预处理执行失败")
            if publishing:
                # Keep published files AND the unpromoted .tmp files as evidence.
                # A failed commit has not established either business terminal.
                try:
                    submissions.uncertain(self.database, operation['operation_id'])
                except Exception:
                    pass  # Preserve the original failure if the ledger is unavailable.
                raise PreprocessError('OPERATION_NEEDS_RECONCILIATION', '发布或终态提交中断，请核对固定运行；不会自动重算',
                                      operation_id=operation['operation_id'], run_id=identifier, cause=structured.code) from error
            if directory.exists():
                try:
                    remove_directory(directory, root)
                except Exception:
                    pass
            try:
                with connect_database(self.database) as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute("UPDATE preprocess_run SET status='failed',error=?,finished_at=? WHERE id=? AND status<>'succeeded'",
                               (json.dumps(structured.as_dict(), ensure_ascii=False), timestamp(), identifier))
                    submissions.finish(db, operation['operation_id'], 'failed', self._get(db, identifier))
            except Exception:
                try:
                    submissions.uncertain(self.database, operation['operation_id'])
                except Exception:
                    pass
                raise structured from error
        finally:
            if temporary.exists():
                try:
                    remove_directory(temporary, root)
                except Exception:
                    pass  # Computation scratch only; never mask execution/commit errors.
        return self.get(identifier)

    def run_batch(self, items):
        """TASK-43: explicit bounded inputs; run() remains the only executor."""
        bound=bind_batch(items)
        parent=submissions.context()
        from .drafts import assert_available
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            operation,fresh=submissions.begin(db,parent,'preprocess.run_batch',{'items':bound})
            if not fresh:
                return submissions.receipt(operation)
            from .retry import parent_reference,state as retry_status
            retry_parent=parent_reference(parent)
            if retry_parent:
                retry_status(db,retry_parent,parent,[item['cube_id'] for item in bound])
            for item in bound:
                if not submissions.admitted(parent,item):
                    assert_available(db,version_id=item['recipe_version_id'])
        if not submissions.claim(self.database,operation['operation_id'],self.executor_id):
            raise DataError('OPERATION_IN_PROGRESS','批量提交已受理，请核对原操作')
        admission=submissions.BatchAdmission(parent.submission_ref,frozenset(tuple(row[k] for k in
            ('cube_id','annotation_version_id','recipe_version_id')) for row in bound))
        token=submissions.current_admission.set(admission)
        try:
            diagnostics=[]
            result=execute_batch(self.run,bound,parent,diagnostics)
            with connect_database(self.database) as db:
                db.execute('BEGIN IMMEDIATE')
                submissions.finish(db,operation['operation_id'],'failed' if result['failed'] else 'succeeded',result)
            return result
        except Exception:
            try:submissions.uncertain(self.database,operation['operation_id'])
            except Exception:pass
            raise
        finally:
            submissions.current_admission.reset(token)

    def check_operation(self, operation_id, owner):
        """Read evidence for exactly one fixed run; this never recomputes or commits success."""
        operation = submissions.get(self.database, operation_id, owner)
        if not operation['run_id']:
            return {**operation, 'run_present':False, 'success_verified':operation['status']=='succeeded'}
        with connect_database(self.database) as db:
            evidence = db.execute('SELECT evidence_root,evidence_directory FROM business_operation WHERE operation_id=?',
                                  (operation_id,)).fetchone()
        try:
            run = self.get(operation['run_id'])
        except DataError:
            return {**operation, 'run_present':False, 'success_verified':False}
        root = Path(evidence[0]).resolve()
        relative = PurePosixPath(evidence[1])
        if relative.is_absolute() or '..' in relative.parts:
            raise PreprocessError('INVALID_ARTIFACT_PATH', '恢复目录无效')
        directory = root.joinpath(*relative.parts).resolve()
        if not directory.is_relative_to(root):
            raise PreprocessError('INVALID_ARTIFACT_PATH', '恢复目录越界')
        files = {name: (directory/name).is_file() for name in ('sample_spectra.npz','report.json')}
        identity_match = False
        if files['report.json']:
            try:
                report = json.loads((directory/'report.json').read_text('utf-8'))
                identity_match = all(report.get(k) == run[k] for k in
                                     ('cube_id','annotation_version_id','recipe_version_id','input_fingerprint')) and report.get('run_id') == run['id']
                with connect_database(self.database) as db:
                    identity = db.execute('SELECT algorithm,sha256 FROM recipe_pipeline_hash WHERE recipe_version_id=?',
                                          (run['recipe_version_id'],)).fetchone()
                identity_match = identity_match and identity == (report.get('recipe_hash_alg'),report.get('recipe_pipeline_sha256'))
            except (OSError, ValueError, TypeError):
                pass
        artifacts = [item for item in run['artifacts'] if item['kind'] in {'sample_spectra','report'}]
        metadata_match = len(artifacts) == 2 and {item['kind'] for item in artifacts} == {'sample_spectra','report'}
        try:
            metadata_match = metadata_match and all(root.joinpath(*PurePosixPath(a['relative_path']).parts).resolve().parent == directory
                and file_sha256(root.joinpath(*PurePosixPath(a['relative_path']).parts)) == a['sha256'] for a in artifacts)
        except OSError:
            metadata_match = False
        return {**operation, 'run_present':True, 'run_status':run['status'], 'files_present':files,
                'report_identity_matches':identity_match, 'artifact_metadata_matches':metadata_match,
                'success_verified':operation['status']=='succeeded' and run['status']=='succeeded' and all(files.values()) and identity_match and metadata_match}

    @projects.checked("preprocess", "identifier")
    def get(self, identifier):
        with connect_database(self.database) as db:
            return self._get(db, identifier)

    @staticmethod
    def _get(db, identifier):
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


def bind_batch(items):
    if type(items) is not list or not items:
        raise DataError("INVALID_REQUEST", "批量输入须为非空列表", fields=["items"])
    if len(items) > 32:
        raise DataError("INVALID_REQUEST", "批量输入超过上限", fields=["items"],
                        limit=32, actual=len(items), reason="batch_too_large")
    keys = {"cube_id", "annotation_version_id", "recipe_version_id"}
    bound, seen = [], set()
    for item in items:
        if type(item) is not dict or set(item) != keys:
            raise DataError("INVALID_REQUEST", "每项须显式指定数据集、标注和配方版本", fields=["items"])
        try:
            if any(type(item[key]) is not str for key in keys):
                raise ValueError("UUID must be a string")
            row = {key: str(UUID(item[key])) for key in keys}
        except (ValueError, AttributeError):
            raise DataError("INVALID_REQUEST", "批量引用须为 UUID", fields=["items"]) from None
        if row["cube_id"] in seen:
            raise DataError("INVALID_REQUEST", "批量数据集不得重复", fields=["items"])
        seen.add(row["cube_id"])
        bound.append(row)
    return bound


def execute_batch(run, bound, parent=None, diagnostics=None):
    """Per-member aggregation, independent of submission registration and IO policy."""
    results = []
    for index, item in enumerate(bound):
        try:
            if parent is None:
                row = run(item["cube_id"], item["annotation_version_id"], item["recipe_version_id"])
            else:
                with submissions.execution_context(submissions.child(parent, index)):
                    row = run(item["cube_id"], item["annotation_version_id"], item["recipe_version_id"])
            results.append({"cube_id": item["cube_id"], "run_id": row["id"], "status": row["status"],
                            "error_code": (row.get("error") or {}).get("error")})
            if diagnostics is not None and row.get('error'):
                append_diagnostic(diagnostics,item,row['error'],row['id'])
        except Exception as error:
            results.append({"cube_id": item["cube_id"], "run_id": error.payload.context.get('run_id') if isinstance(error, DataError) else None, "status": "failed",
                            "error_code": error.code if isinstance(error, DataError) else "PREPROCESS_RUN_FAILED"})
            if diagnostics is not None and isinstance(error,DataError):
                append_diagnostic(diagnostics,item,error.as_dict(),error.payload.context.get('run_id'))
    result = {"items": results, "succeeded": sum(row["status"] == "succeeded" for row in results),
              "failed": sum(row["status"] == "failed" for row in results), "truncated": False}
    if diagnostics:
        result['diagnostics']=diagnostics
    # Match the compact UTF-8 JSON emitted by the HTTP response; never truncate.
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")) > 8*1024*1024:
        raise DataError("INVALID_REQUEST", "批量响应超过上限", fields=["response"],
                        limit=8388608, reason="batch_response_too_large")
    return result


def append_diagnostic(diagnostics,item,error,run_id):
    from spectrumagent.data.validation import PARAMETER_ERRORS,public_error
    if error.get('error') in PARAMETER_ERRORS and len(diagnostics)<32:
        safe=public_error(error)
        diagnostics.append({'cube_id':item['cube_id'],'run_id':run_id,'error':safe['error'],'detail':safe['detail'],
                            'fields':safe['context'].get('fields',[])})
