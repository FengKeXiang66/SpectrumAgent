"""TASK-32: explicit, bounded ENVI export using the completed run's frozen report."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from uuid import uuid4

import numpy as np
from pydantic import ValidationError

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.data.readers.binary import mapped_dataset
from spectrumagent.data.readers.header import normalize
from spectrumagent.storage import guard as storage
from . import builtin_registry
from .operators.pca import transform
from .operators.reflectance import reflectance
from .registry import PreprocessError
from .run import file_sha256, peak_rss, timestamp
from .schema import ReflectanceParams


BLOCK_SIZE = 32
FITTED_OPS = {"pca", "mnf", "ica"}
METHOD_A = FITTED_OPS | {"snv"}
METHOD_B = {"standardize", "continuum"}
METHOD_C = {"sg_smooth", "sg_derivative", "crop", "resample"}


def mismatch():
    return PreprocessError("EXPORT_CALIBRATION_MISMATCH", "report 冻结参数或校验字段不一致")


def canonical_hash(value):
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(text.encode("utf-8")).hexdigest()


def artifact_path(root, value):
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "\\" in value or ":" in value:
        raise DataError("INVALID_ARTIFACT_PATH", "产物须为 POSIX 相对路径")
    root = Path(root).resolve()
    target = root.joinpath(*relative.parts).resolve()
    if not target.is_relative_to(root):
        raise DataError("INVALID_ARTIFACT_PATH", "产物路径越出输出根")
    return target


class ReportReplay:
    def __init__(self, report):
        self.report = report
        if any(step["op"] in {"msc", "emsc"} for step in report["steps"]):
            raise PreprocessError("EXPORT_OPERATOR_NOT_REPLAYABLE", "此算子暂不支持冻结重放",
                                  reason="参考谱未随 report 落盘、阶段二未开放")
        self.steps, self.checks = [], []
        registry = builtin_registry()
        try:
            b01 = report["b01"]
            if set(b01["params"]) != set(ReflectanceParams.model_fields):
                raise mismatch()
            self.b01_params = ReflectanceParams.model_validate(b01["params"]).model_dump()
            self.b01_meta = b01["meta"]
            for step in report["steps"]:
                op, meta = step["op"], step["meta"]
                if op not in METHOD_A | METHOD_B | METHOD_C:
                    raise mismatch()
                entry = registry.resolve(op, step["version"])
                params = entry.model.model_validate(step["params"]).model_dump()
                method_class = "A" if op in METHOD_A else "B" if op in METHOD_B else "C"
                if method_class == "A" and meta["method"] != op:
                    raise mismatch()
                if method_class == "B" and meta["method"] != params["method"]:
                    raise mismatch()
                if op == "standardize":
                    fitted = meta["fitted"]
                    if params["method"] in {"area", "vector"}:
                        if fitted != []:
                            raise mismatch()
                    else:
                        keys = {"mean", "std"} if params["method"] == "standard" else {"min", "max"}
                        if not fitted or any(set(row) != keys for row in fitted):
                            raise mismatch()
                check = {"op": op, "version": step["version"], "method_class": method_class,
                         "method_check": "not_applicable" if method_class == "C" else "matched"}
                if "axis_len" not in meta:
                    if "axis_sha256" in meta or op in FITTED_OPS | {"crop", "resample"}:
                        raise mismatch()
                    check.update(axis_branch=1, axis_len=None, axis_sha256=None, axis_digest_match=None)
                elif meta["axis_len"] is None:
                    if meta["axis_sha256"] is not None or op not in FITTED_OPS:
                        raise mismatch()
                    check.update(axis_branch=2, axis_len=None, axis_sha256=None, axis_digest_match=None)
                else:
                    if (op not in {"crop", "resample"} or type(meta["axis_len"]) is not int
                            or not isinstance(meta["axis_sha256"], str)
                            or re.fullmatch(r"[0-9a-f]{64}", meta["axis_sha256"]) is None):
                        raise mismatch()
                    if op == "crop":
                        source = np.asarray(params["source"], dtype=np.float64)
                        lo, hi = params["range"]
                        axis = source[(source >= lo) & (source <= hi)]
                    else:
                        axis = np.asarray(params["target"], dtype=np.float64)
                    digest = sha256(np.ascontiguousarray(axis).tobytes(order="C")).hexdigest()
                    if len(axis) != meta["axis_len"] or digest != meta["axis_sha256"]:
                        raise mismatch()
                    check.update(axis_branch=3, axis_len=len(axis), axis_sha256=digest, axis_digest_match=True)
                # No declaration in branch 1 does not establish an output axis.
                check["wavelengths_present"] = None if check["axis_branch"] == 1 else check["axis_branch"] == 3
                self.steps.append((op, params, meta, entry.impl, check))
                self.checks.append(check)
        except (KeyError, TypeError, ValueError, IndexError, ValidationError) as error:
            raise mismatch() from error
        frozen = [{"op": step["op"], "version": step["version"], "meta": step["meta"]}
                  for step in report["steps"] if step["op"] in FITTED_OPS
                  or (step["op"] == "standardize" and step["params"]["method"] in {"standard", "minmax"})]
        self.fit_signature = canonical_hash(frozen)

    def apply(self, spectra):
        try:
            result, b01_meta = reflectance(spectra, deepcopy(self.b01_params))
            if any(b01_meta[key] != self.b01_meta[key] for key in ("branch", "guard")):
                raise mismatch()
            for op, params, meta, impl, check in self.steps:
                if op == "standardize" and params["method"] in {"standard", "minmax"}:
                    fitted = meta["fitted"]
                    if len(fitted) != result.shape[1]:
                        raise mismatch()
                    if params["method"] == "standard":
                        offset = np.asarray([row["mean"] for row in fitted], dtype=np.float64)
                        scale = np.asarray([row["std"] for row in fitted], dtype=np.float64)
                    else:
                        offset = np.asarray([row["min"] for row in fitted], dtype=np.float64)
                        scale = np.asarray([row["max"] for row in fitted], dtype=np.float64) - offset
                    if not np.isfinite(offset).all() or not np.isfinite(scale).all() or np.any(scale < 0):
                        raise mismatch()
                    zero = scale == 0
                    if zero.any() and params["zero_std"] == "error":
                        raise mismatch()
                    with np.errstate(divide="ignore", invalid="ignore"):
                        result = (result-offset)/scale
                    result[:, zero] = 0. if params["zero_std"] == "zeros" else np.nan
                elif op in FITTED_OPS:
                    mean = np.asarray(meta["mean"], dtype=np.float64)
                    loadings = np.asarray(meta["loadings"], dtype=np.float64)
                    if (mean.shape != (result.shape[1],) or loadings.ndim != 2
                            or loadings.shape[0] != result.shape[1] or loadings.shape[1] == 0
                            or not np.isfinite(mean).all() or not np.isfinite(loadings).all()):
                        raise mismatch()
                    result = np.concatenate([transform(row[None, :], mean, loadings) for row in result])
                    if result.shape[1] != loadings.shape[1]:
                        raise mismatch()
                else:
                    outputs = []
                    for row in result:
                        output = impl(row[None, :], deepcopy(params))
                        outputs.append(output[0] if isinstance(output, tuple) else output)
                    result = np.concatenate(outputs)
                if check["axis_branch"] == 3 and result.shape[1] != check["axis_len"]:
                    raise mismatch()
            return result
        except (KeyError, TypeError, ValueError, IndexError, DataError) as error:
            if isinstance(error, PreprocessError) and error.code == "EXPORT_CALIBRATION_MISMATCH":
                raise
            raise mismatch() from error


def replay_from_report(report, spectra):
    return ReportReplay(report).apply(spectra)


def raw_dataset(stored):
    """Bind registered physical metadata; source header is never a calibration source."""
    fields = dict(lines=stored.shape[0], samples=stored.shape[1], bands=stored.shape[2],
                  data_type=stored.dtype, interleave=stored.interleave,
                  byte_order=stored.metadata["byte_order"], header_offset=stored.metadata["header_offset"])
    return mapped_dataset(Path(stored.header_path), normalize(fields), stored.data_path, raw=True)


def envi_header(shape, wavelengths):
    lines, samples, bands = shape
    text = (f"ENVI\nsamples = {samples}\nlines = {lines}\nbands = {bands}\n"
            "data type = 4\ninterleave = bsq\nbyte order = 0\nheader offset = 0\n"
            "data file = processed_cube.img\n")
    if wavelengths:
        text += "wavelength = {" + ", ".join(repr(float(value)) for value in wavelengths) + "}\n"
    return text


def export_run(runner, identifier):
    with connect_database(runner.database) as db:
        row = db.execute("SELECT cube_id,status FROM preprocess_run WHERE id=?", (identifier,)).fetchone()
        if row is None:
            error = PreprocessError("RUN_NOT_FOUND", "run 不存在")
            error.status_code = 404
            raise error
        if row[1] != "succeeded":
            raise PreprocessError("EXPORT_RUN_NOT_READY", "仅可导出已成功的 run")
        entry = db.execute("SELECT relative_path FROM preprocess_artifact WHERE run_id=? AND kind='report'",
                           (identifier,)).fetchone()
    root = runner.paths.artifact_root
    guard = storage.for_database(runner.database)
    if guard.output_root is not None and not guard.output_root_available:
        # An unavailable root may also make report reads fail. Let the existing
        # guard return its structured refusal before touching that filesystem.
        storage.resolve_write(root/"processed_cube.img.tmp", kind="EXPORT_CREATE")
    if entry is None:
        raise mismatch()
    report_path = artifact_path(root, entry[0])
    report = json.loads(report_path.read_text("utf-8"))
    replay = ReportReplay(report)  # Reject unsupported operators before any file write.
    stored, _ = runner.registry.get(row[0])
    dataset = raw_dataset(stored)
    first = dataset.read_region(0, 1, 0, stored.shape[1])
    output_bands = replay.apply(first[0]).shape[1]
    del first, dataset
    lines, samples, input_bands = stored.shape
    axis = report["wavelengths"]
    wavelengths = axis if axis and len(axis) == output_bands else None
    directory = report_path.parent
    targets = [directory/name for name in ("processed_cube.img", "processed_cube.hdr", "export_manifest.json")]
    temporary = [path.with_name(path.name+".tmp") for path in targets]
    started = False
    rss = peak_rss()
    try:
        image = storage.resolve_write(temporary[0], kind="EXPORT_CREATE")
        started = True
        # Seeked BSQ band slices keep both source and output resident memory bounded.
        with image.open("w+b") as stream:
            stream.truncate(lines*samples*output_bands*4)
            for l0 in range(0, lines, BLOCK_SIZE):
                dataset = raw_dataset(stored)
                block = dataset.read_region(l0, min(l0+BLOCK_SIZE, lines), 0, samples)
                converted = np.empty((len(block), samples, output_bands), dtype="<f4")
                for offset, line in enumerate(block):
                    converted[offset] = replay.apply(line)
                for band in range(output_bands):
                    stream.seek((band*lines+l0)*samples*4)
                    stream.write(np.ascontiguousarray(converted[:, :, band]).tobytes())
                rss = max(rss, peak_rss())
                del block, dataset, line, converted
        image_hash = file_sha256(image)
        header = storage.resolve_write(temporary[1], kind="EXPORT_HEADER")
        header.write_text(envi_header((lines, samples, output_bands), wavelengths), encoding="utf-8")
        artifacts = [{"kind": "processed_cube", "relative_path": target.relative_to(root).as_posix(),
                      "sha256": digest, "bytes": source.stat().st_size}
                     for target, source, digest in ((targets[0], image, image_hash),
                                                     (targets[1], header, file_sha256(header)))]
        manifest = {key: report[key] for key in ("run_id", "recipe_pipeline_sha256", "recipe_hash_alg",
                                                "input_fingerprint", "code_version")}
        manifest.update(scope="full_cube", input_bands=input_bands, output_bands=output_bands,
                        fitting_pixels=report["fitting_source"]["n_spectra"],
                        transform_chain=[{"op": step["op"], "version": step["version"]} for step in report["steps"]],
                        fit_signature=replay.fit_signature, b01_params_source="report.b01.params",
                        b01_method_class="C", b01_method_check="not_applicable", steps=replay.checks,
                        band_axis_source="report.wavelengths" if wavelengths else "omitted",
                        omission_reasons={"wavelengths": None if wavelengths else "absent or length differs from output_bands",
                                          "fwhm": "TASK-32 D6: source fwhm is never copied"},
                        wavelengths_present=bool(wavelengths),
                        envi={"shape": [lines, samples, output_bands], "dtype": "float32", "interleave": "bsq",
                              "wavelengths": {"count": len(wavelengths) if wavelengths else 0,
                                              "sha256": canonical_hash(wavelengths) if wavelengths else None}},
                        artifacts=artifacts, peak_rss_bytes=max(rss, peak_rss()), exported_at=timestamp())
        storage.resolve_write(temporary[2], kind="EXPORT_MANIFEST").write_text(
            json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
        for source, target in zip(temporary, targets):
            storage.replace(source, target)
        with connect_database(runner.database) as db:
            for item in artifacts:
                db.execute("INSERT INTO preprocess_artifact (id,run_id,kind,relative_path,sha256,created_at) "
                           "VALUES (?,?,?,?,?,?) ON CONFLICT(run_id,kind,relative_path) DO UPDATE SET "
                           "sha256=excluded.sha256,created_at=excluded.created_at",
                           (str(uuid4()), identifier, item["kind"], item["relative_path"], item["sha256"], manifest["exported_at"]))
        return {"run_id": identifier, "status": "succeeded", "scope": "full_cube", "artifacts": artifacts,
                "manifest_relative_path": targets[2].relative_to(root).as_posix()}
    except Exception:
        if started:
            for path in [*temporary, *targets]:
                if path.exists():
                    storage.unlink(path)
            with connect_database(runner.database) as db:
                db.execute("DELETE FROM preprocess_artifact WHERE run_id=? AND kind='processed_cube'", (identifier,))
        raise
