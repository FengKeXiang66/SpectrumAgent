"""Read-only archives and explicit ROI extraction, before any model fitting."""
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import minimum_filter, maximum_filter

from spectrumagent.data import DataError
from spectrumagent.data.readers import open_envi


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise DataError("EXPERIMENT_INPUT_INVALID", "输入须为存在的绝对文件路径", path=str(path))
    return path.resolve()


def record_source(path, manifest):
    path = source_path(path)
    key = str(path)
    if key not in manifest:
        manifest[key] = {"path": key, "size": path.stat().st_size, "sha256": sha256(path)}
    return path


def check_sources(manifest):
    for item in manifest.values():
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != item["size"] or sha256(path) != item["sha256"]:
            raise DataError("SOURCE_CHANGED", "实验读取期间源文件变化", path=str(path))


@dataclass
class Samples:
    X: np.ndarray
    y: np.ndarray
    origins: list[dict]
    sources: dict
    unit: str
    excluded: int = 0


def mapping_weights(source, target, window, nearest_tolerance):
    source, target = np.asarray(source), np.asarray(target)
    if not len(source) or not np.isfinite(source).all() or len(np.unique(source)) != len(source):
        raise DataError("EXPERIMENT_AXIS_INVALID", "原始波长须有限且互异")
    weights = np.zeros((len(source), len(target)), np.float32)
    for column, value in enumerate(target):
        indices = np.flatnonzero((source >= value - window / 2) & (source < value + window / 2))
        if not len(indices):
            nearest = int(np.argmin(np.abs(source - value)))
            if abs(source[nearest] - value) > nearest_tolerance:
                raise DataError("EXPERIMENT_AXIS_INVALID", "目标波长附近没有可用通道", wavelength_nm=float(value))
            indices = np.asarray([nearest])
        weights[indices, column] = 1 / len(indices)
    return weights


def quality_mask(mapped, used, quality):
    valid = (np.isfinite(mapped).all(axis=-1) & (mapped.mean(axis=-1) > quality.min_mean)
             & (mapped.std(axis=-1) > quality.min_std)
             & ((used == 0).mean(axis=-1) <= quality.max_zero_fraction))
    if quality.saturation is not None:
        valid &= (used < quality.saturation).all(axis=-1)
    return valid


def roi_maps(path, shape, classes, header_hash=None):
    """Separate region identities prevent mixing adjacent ROIs of the same class."""
    if path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as archive:
            regions, labels = archive["region_map"].copy(), archive["label_map"].copy()
    elif path.suffix.lower() == ".json":
        document = json.loads(path.read_text("utf-8-sig"))
        if document.get("material_confirmed") is False:
            raise DataError("EXPERIMENT_ROI_INVALID", "标注文件明确标记为未确认")
        signature = document.get("source_signature", {}).get("hdr_sha256")
        if signature and signature != header_hash:
            raise DataError("EXPERIMENT_ROI_INVALID", "标注绑定的HDR与当前原图不同")
        if document.get("imageHeight") != shape[0] or document.get("imageWidth") != shape[1]:
            raise DataError("EXPERIMENT_ROI_INVALID", "ROI声明尺寸与原图不同")
        regions = np.zeros(shape, np.int32)
        labels = np.zeros(shape, np.int64)
        names = {name: label for label, name in classes.items()}
        for index, region in enumerate(document["shapes"], 1):
            label = names.get(region.get("label"))
            if label is None:
                raise DataError("EXPERIMENT_ROI_INVALID", "ROI类别未在实验中声明")
            points = np.asarray(region.get("points"), dtype=float)
            if (points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all()
                    or np.any(points < 0) or np.any(points[:, 0] >= shape[1]) or np.any(points[:, 1] >= shape[0])):
                raise DataError("EXPERIMENT_ROI_INVALID", "ROI坐标非法或越界")
            mask = Image.new("1", (shape[1], shape[0]))
            draw = ImageDraw.Draw(mask)
            if region.get("shape_type") == "rectangle" and len(points) == 2:
                low, high = np.floor(points.min(axis=0)), np.floor(points.max(axis=0))
                draw.rectangle([tuple(low), tuple(high)], fill=1)
            elif region.get("shape_type") == "polygon" and len(points) >= 3:
                draw.polygon([tuple(p) for p in points], fill=1)
            else:
                raise DataError("EXPERIMENT_ROI_INVALID", "仅支持rectangle或polygon区域")
            selected = np.asarray(mask, dtype=bool)
            if np.any(regions[selected] != 0):
                raise DataError("EXPERIMENT_ROI_INVALID", "ROI重叠，请先消除歧义")
            regions[selected], labels[selected] = index, label
    else:
        raise DataError("EXPERIMENT_ROI_INVALID", "ROI须为JSON或含region_map/label_map的NPZ")
    if (regions.shape != shape or labels.shape != shape or regions.dtype.kind not in "iu"
            or labels.dtype.kind not in "iu" or np.any(regions < 0)):
        raise DataError("EXPERIMENT_ROI_INVALID", "ROI位图形状或编码不合法")
    for region in np.unique(regions[regions > 0]):
        values = np.unique(labels[regions == region])
        if len(values) != 1 or int(values[0]) not in classes:
            raise DataError("EXPERIMENT_ROI_INVALID", "每个ROI必须对应唯一声明类别")
    return regions, labels


def archives(spec, target):
    arrays, labels, origins, manifest, seen = [], [], [], {}, set()
    for value in spec.paths:
        path = Path(value)
        candidates = sorted(path.rglob("*.npz")) if path.is_dir() else [path]
        for candidate in candidates:
            path = record_source(candidate, manifest)
            if path in seen:
                raise DataError("EXPERIMENT_INPUT_INVALID", "输入文件重复", path=str(path))
            seen.add(path)
            with np.load(path, allow_pickle=False) as archive:
                X, y = archive[spec.spectra_key].copy(), archive[spec.labels_key].copy()
                waves = archive[spec.wavelengths_key]
                if waves.shape != (len(target),) or not np.array_equal(waves, target):
                    raise DataError("EXPERIMENT_AXIS_INVALID", "冻结光谱波长轴不匹配，不能按列号猜测")
            arrays.append(X)
            labels.append(y)
            origins.extend({"source": str(path), "index": i} for i in range(len(y)))
    if not arrays:
        raise DataError("EXPERIMENT_INPUT_INVALID", "没有找到NPZ输入")
    return Samples(np.concatenate(arrays), np.concatenate(labels), origins, manifest, spec.evaluation_unit)


def image_samples(spec, target, classes):
    arrays, labels, origins, manifest, excluded = [], [], [], {}, 0
    for member in spec.members:
        header = record_source(member.header_path, manifest)
        roi = record_source(member.roi_path, manifest)
        explicit = record_source(member.data_path, manifest) if member.data_path else None
        dataset = open_envi(header, explicit, raw=True)
        record_source(dataset.data_path, manifest)
        if spec.neighborhood > min(dataset.shape[:2]):
            raise DataError("EXPERIMENT_ROI_INVALID", "空间邻域大于图像尺寸")
        source = np.asarray(dataset.wavelengths) * (1000 if spec.wavelength_unit == "um" else 1)
        unit = str(dataset.metadata.get("wavelength units", "")).lower()
        if unit and ((spec.wavelength_unit == "nm" and unit not in ("nm", "nanometers", "nanometres"))
                     or (spec.wavelength_unit == "um" and unit not in ("um", "μm", "micrometers", "microns"))):
            raise DataError("EXPERIMENT_AXIS_INVALID", "声明单位与HDR波长单位冲突")
        weights = mapping_weights(source, target, spec.mapping_window_nm, spec.nearest_tolerance_nm)
        regions, truth = roi_maps(roi, dataset.shape[:2], classes, manifest[str(header)]["sha256"])
        center_mask = regions > 0
        order = None
        if member.centers_path:
            centers = record_source(member.centers_path, manifest)
            with centers.open(encoding="utf-8-sig", newline="") as stream:
                order = [(int(r["row"]), int(r["col"])) for r in csv.DictReader(stream)]
            if len(set(order)) != len(order) or not order:
                raise DataError("EXPERIMENT_INPUT_INVALID", "中心坐标须非空且不重复")
            center_mask = np.zeros(dataset.shape[:2], bool)
            for row, col in order:
                if not 0 <= row < dataset.shape[0] or not 0 <= col < dataset.shape[1] or regions[row, col] == 0:
                    raise DataError("EXPERIMENT_ROI_INVALID", "指定中心越界或不在ROI内")
                center_mask[row, col] = True
        radius = spec.neighborhood // 2
        member_rows = {}
        for first in range(0, dataset.shape[0], 32):
            last = min(first + 32, dataset.shape[0])
            low, high = max(0, first-radius), min(dataset.shape[0], last+radius)
            raw = dataset.read_region(low, high, 0, dataset.shape[1])
            if np.iscomplexobj(raw):
                raise DataError("EXPERIMENT_INPUT_INVALID", "不支持复数光谱")
            raw = raw.astype(np.float64)
            mapped = (raw / float(dataset.metadata["scale_factor"])) @ weights
            used = raw[:, :, weights.sum(axis=1) > 0]
            valid = quality_mask(mapped, used, spec.quality)
            region_block = regions[low:high]
            minimum = minimum_filter(region_block, spec.neighborhood, mode="constant", cval=0)
            maximum = maximum_filter(region_block, spec.neighborhood, mode="constant", cval=0)
            safe = (minimum > 0) & (minimum == maximum)
            safe &= minimum_filter(valid.astype(np.uint8), spec.neighborhood, mode="constant", cval=0) > 0
            for row, col in np.argwhere(center_mask[first:last]):
                row += first
                local = row-low
                if not safe[local, col]:
                    excluded += 1
                    continue
                # Explicit sum order matches the archived neighborhood extraction.
                total = np.zeros(len(target), np.float64)
                for dr in range(-radius, radius+1):
                    for dc in range(-radius, radius+1):
                        total += mapped[local+dr, col+dc]
                member_rows[(int(row), int(col))] = (total / spec.neighborhood**2).astype(np.float32)
        selected = [position for position in (order if order is not None else sorted(member_rows)) if position in member_rows]
        if selected:
            arrays.append(np.stack([member_rows[p] for p in selected]))
            labels.append(np.asarray([truth[p] for p in selected], np.int64))
            origins.extend({"source": str(header), "sample_id": member.sample_id, "row": r, "col": c,
                            "region": int(regions[r, c])} for r, c in selected)
    if not arrays:
        raise DataError("EXPERIMENT_INPUT_INVALID", "没有通过ROI邻域与质量检查的中心")
    return Samples(np.concatenate(arrays), np.concatenate(labels), origins, manifest, spec.evaluation_unit, excluded)


def load_input(spec, target, classes):
    try:
        data = archives(spec, target) if spec.kind == "npz" else image_samples(spec, target, classes)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DataError("EXPERIMENT_INPUT_INVALID", "无法按声明读取输入", reason=str(error)) from error
    if (data.X.ndim != 2 or data.X.shape != (len(data.y), len(target)) or data.y.ndim != 1
            or not len(data.y) or data.X.dtype.kind not in "iuf" or data.y.dtype.kind not in "iu"
            or not np.isfinite(data.X).all() or not np.isin(data.y, list(classes)).all()):
        raise DataError("EXPERIMENT_INPUT_INVALID", "需要有限二维光谱、同长整数标签和声明类别")
    check_sources(data.sources)
    return data


def check_split(train, test):
    if set(train.sources) & set(test.sources):
        raise DataError("EXPERIMENT_SPLIT_OVERLAP", "训练与测试引用了相同文件")
    a = {row.get("sample_id") for row in train.origins if row.get("sample_id")}
    b = {row.get("sample_id") for row in test.origins if row.get("sample_id")}
    if a & b:
        raise DataError("EXPERIMENT_SPLIT_OVERLAP", "训练与测试包含相同sample_id")
    tokens = {hashlib.sha256(np.asarray(row, dtype="<f8").tobytes()).digest() for row in train.X}
    if any(hashlib.sha256(np.asarray(row, dtype="<f8").tobytes()).digest() in tokens for row in test.X):
        raise DataError("EXPERIMENT_SPLIT_OVERLAP", "训练与测试存在完全相同的数值光谱")
