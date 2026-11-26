"""Read-only archives and explicit ROI extraction, before any model fitting."""
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PureWindowsPath

import numpy as np
from PIL import Image, ImageDraw

from spectrumagent.data import DataError
from spectrumagent.data.readers import open_envi

WAVELENGTH_UNITS = {
    'nm': ('nm', 'nanometers', 'nanometres'),
    'um': ('um', 'μm', 'µm', 'micrometers', 'microns'),
}


def sha256(path, check=None):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while True:
            if check:
                check()
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()



def file_snapshot(path, check=None):
    """Get an identity that also changes when the modification time is restored."""
    import os
    if check:
        check()
    with Path(path).open('rb') as stream:
        stat = os.fstat(stream.fileno())
        change = stat.st_ctime_ns
        if os.name == 'nt':
            # Windows st_ctime is creation time. Query NTFS/SMB ChangeTime.
            change = _windows_change_time(stream)
    return {'size':stat.st_size, 'mtime_ns':stat.st_mtime_ns, 'change_time':change,
            'device':stat.st_dev, 'file_id':stat.st_ino}


def _windows_change_time(stream):
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class BasicInfo(ctypes.Structure):
        _fields_ = [('creation', ctypes.c_int64), ('access', ctypes.c_int64),
                    ('write', ctypes.c_int64), ('change', ctypes.c_int64), ('attributes', wintypes.DWORD)]

    info = BasicInfo()
    get_info = ctypes.WinDLL('kernel32', use_last_error=True).GetFileInformationByHandleEx
    get_info.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    get_info.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(stream.fileno())
    if get_info(handle, 0, ctypes.byref(info), ctypes.sizeof(info)) and info.change:
        return info.change
    return None


class CheckedStream:
    """Insert cancellation checks into standard ZIP, CSV and image stream operations."""
    def __init__(self, stream, check):
        self.stream, self.check = stream, check

    def read(self, *args):
        self.check()
        return self.stream.read(*args)

    def write(self, data):
        self.check()
        return self.stream.write(data)

    def fileno(self):
        from io import UnsupportedOperation
        raise UnsupportedOperation('Use the checked stream operations')

    def __getattr__(self, name):
        return getattr(self.stream, name)

def source_path(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise DataError("EXPERIMENT_INPUT_INVALID", "输入须为存在的绝对文件路径", path=str(path))
    return path.resolve()


def record_source(path, manifest, check=None):
    path = source_path(path)
    key = str(path)
    if key not in manifest:
        manifest[key] = {"path": key, "size": path.stat().st_size, "sha256": sha256(path, check)}
    return path


def check_sources(manifest, check=None):
    for item in manifest.values():
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != item["size"] or sha256(path, check) != item["sha256"]:
            raise DataError("SOURCE_CHANGED", "实验读取期间源文件变化", path=str(path))


@dataclass
class Samples:
    X: np.ndarray
    y: np.ndarray
    origins: list[dict]
    sources: dict
    unit: str
    excluded: int = 0
    sampling: dict | None = None


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
            boundary = np.asarray([shape[1], shape[0]])
            if (points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all()
                    or np.any(points < 0) or np.any(points > boundary)):
                raise DataError("EXPERIMENT_ROI_INVALID", "ROI坐标非法或越界")
            points = np.where(points == boundary, boundary - 1, points)
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


def archives(spec, target, check=None):
    arrays, labels, origins, manifest, seen = [], [], [], {}, set()
    for value in spec.paths:
        path = Path(value)
        candidates = archive_files(path)
        for candidate in candidates:
            path = record_source(candidate, manifest, check)
            if path in seen:
                raise DataError("EXPERIMENT_INPUT_INVALID", "输入文件重复", path=str(path))
            seen.add(path)
            with np.load(path, allow_pickle=False) as archive:
                X, y = archive[spec.spectra_key].copy(), archive[spec.labels_key].copy()
                waves = archive[spec.wavelengths_key]
                if waves.shape != (len(target),) or not np.array_equal(waves, target):
                    raise DataError("EXPERIMENT_AXIS_INVALID", "冻结光谱波长轴不匹配，不能按列号猜测")
                groups = None
                if spec.groups_key:
                    values = archive[spec.groups_key]
                    if values.shape != y.shape or values.dtype.kind not in 'iuUS':
                        raise DataError('EXPERIMENT_GROUPS_INVALID', 'NPZ分组字段必须为逐条对应的整型或字符串')
                    groups = values.astype(str).tolist()
                    if any(not value.strip() for value in groups):
                        raise DataError('EXPERIMENT_GROUPS_INVALID', 'NPZ分组字段含空组')
            arrays.append(X)
            labels.append(y)
            origins.extend({"source": str(path), "index": i, **({"sample_id":groups[i]} if groups is not None else {})}
                           for i in range(len(y)))
    if not arrays:
        raise DataError("EXPERIMENT_INPUT_INVALID", "没有找到NPZ输入")
    return Samples(np.concatenate(arrays), np.concatenate(labels), origins, manifest, spec.evaluation_unit)


def image_samples(spec, target, classes, progress=None):
    from scipy.ndimage import minimum_filter, maximum_filter

    arrays, labels, origins, manifest, excluded = [], [], [], {}, 0
    for file_index, member in enumerate(spec.members, 1):
        def report(rows_done=0, rows_total=None):
            if progress:
                progress(file_index=file_index, file_total=len(spec.members), rows_done=rows_done, rows_total=rows_total)

        report()
        header = record_source(member.header_path, manifest, progress)
        roi = record_source(member.roi_path, manifest, progress)
        explicit = source_path(member.data_path) if member.data_path else None
        dataset = open_envi(header, explicit, raw=True)
        report(rows_total=dataset.shape[0])
        record_source(dataset.data_path, manifest, progress)
        if spec.neighborhood > min(dataset.shape[:2]):
            raise DataError("EXPERIMENT_ROI_INVALID", "空间邻域大于图像尺寸")
        source = np.asarray(dataset.wavelengths) * (1000 if spec.wavelength_unit == "um" else 1)
        unit = str(dataset.metadata.get("wavelength units", "")).lower()
        if unit and unit not in WAVELENGTH_UNITS[spec.wavelength_unit]:
            raise DataError("EXPERIMENT_AXIS_INVALID", "声明单位与HDR波长单位冲突")
        weights = mapping_weights(source, target, spec.mapping_window_nm, spec.nearest_tolerance_nm)
        regions, truth = roi_maps(roi, dataset.shape[:2], classes, manifest[str(header)]["sha256"])
        center_mask = regions > 0
        order = None
        if member.centers_path:
            centers = record_source(member.centers_path, manifest, progress)
            with centers.open(encoding="utf-8-sig", newline="") as stream:
                order = [(int(r["row"]), int(r["col"])) for r in csv.DictReader(stream)]
            if len(set(order)) != len(order) or not order:
                raise DataError("EXPERIMENT_INPUT_INVALID", "中心坐标须非空且不重复")
            center_mask = np.zeros(dataset.shape[:2], bool)
            for row, col in order:
                if not 0 <= row < dataset.shape[0] or not 0 <= col < dataset.shape[1] or regions[row, col] == 0:
                    raise DataError("EXPERIMENT_ROI_INVALID", "指定中心越界或不在ROI内")
                center_mask[row, col] = True
        elif spec.sampling_stride > 1:
            center_mask = np.zeros(dataset.shape[:2], bool)
            stride = spec.sampling_stride
            center_mask[::stride, ::stride] = regions[::stride, ::stride] > 0
        radius = spec.neighborhood // 2
        member_rows = {}
        for first in range(0, dataset.shape[0], 32):
            if progress:
                progress()
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
            report(last, dataset.shape[0])
        selected = [position for position in (order if order is not None else sorted(member_rows)) if position in member_rows]
        if selected:
            arrays.append(np.stack([member_rows[p] for p in selected]))
            labels.append(np.asarray([truth[p] for p in selected], np.int64))
            origins.extend({"source": str(header), "sample_id": member.sample_id, "row": r, "col": c,
                            "region": int(regions[r, c]), **({'batch':member.batch} if member.batch else {})} for r, c in selected)
    if not arrays:
        raise DataError("EXPERIMENT_INPUT_INVALID", "没有通过ROI邻域与质量检查的中心")
    X, y = np.concatenate(arrays), np.concatenate(labels)
    sampling = None
    if spec.max_per_class is not None:
        rng = np.random.default_rng(spec.sampling_seed)
        selected = []
        counts = {}
        for label in sorted(classes):
            indices = np.flatnonzero(y == label)
            count = min(len(indices), spec.max_per_class)
            chosen = rng.choice(indices, count, replace=False) if count < len(indices) else indices
            selected.extend(chosen)
            counts[str(label)] = {'eligible':len(indices), 'selected':count}
        selected = sorted(selected)
        X, y, origins = X[selected], y[selected], [origins[i] for i in selected]
        sampling = {'max_per_class':spec.max_per_class, 'sampling_seed':spec.sampling_seed, 'class_counts':counts}
    return Samples(X, y, origins, manifest, spec.evaluation_unit, excluded, sampling)


def load_input(spec, target, classes, progress=None):
    try:
        data = archives(spec, target, progress) if spec.kind == "npz" else image_samples(spec, target, classes, progress)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise DataError("EXPERIMENT_INPUT_INVALID", "无法按声明读取输入", reason=str(error)) from error
    if (data.X.ndim != 2 or data.X.shape != (len(data.y), len(target)) or data.y.ndim != 1
            or not len(data.y) or data.X.dtype.kind not in "iuf" or data.y.dtype.kind not in "iu"
            or not np.isfinite(data.X).all() or not np.isin(data.y, list(classes)).all()):
        raise DataError("EXPERIMENT_INPUT_INVALID", "需要有限二维光谱、同长整数标签和声明类别")
    check_sources(data.sources, progress)
    return data


def archive_files(path):
    return sorted(path.rglob("*.npz")) if path.is_dir() else [path]


def sample_ids(spec):
    if spec.kind == 'npz':
        return set(), False
    ids = [member.sample_id if member.sample_id != member.header_path else None for member in spec.members]
    return {item for item in ids if item}, all(ids)


def sample_label(value):
    # Existing user-supplied IDs can be paths, including paths from another OS.
    return PureWindowsPath(value).name if '/' in value or '\\' in value else value


def split_preflight(config, fingerprints=None, *, check=None):
    """Read file identities and hash bytes without extracting ROI spectra."""
    paths, sides = {}, []
    for spec in (config.train, config.test):
        files, originals, content_files = set(), set(), set()
        if spec.kind == 'npz':
            files.update(source_path(file) for value in spec.paths for file in archive_files(Path(value)))
            if not files:
                raise DataError('EXPERIMENT_INPUT_INVALID', '没有找到 NPZ 输入')
            content_files.update(files)
        else:
            for member in spec.members:
                dataset = open_envi(member.header_path, member.data_path, raw=True)
                originals.add(source_path(dataset.header_path))
                binary = source_path(dataset.data_path)
                content_files.add(binary)
                files.update((source_path(dataset.header_path), binary, source_path(member.roi_path)))
                if member.centers_path:
                    files.add(source_path(member.centers_path))
        for file in files:
            key = str(file)
            if key not in paths:
                paths[key] = fingerprints[key]['sha256'] if fingerprints is not None else sha256(file, check)
        sides.append((files, originals, content_files, *sample_ids(spec)))
    (train, train_images, train_content, train_ids, train_known), (test, test_images, test_content, test_ids, test_known) = sides
    test_by_digest = {}
    for file in sorted(test_content - train):
        test_by_digest.setdefault(paths[str(file)], []).append(file)
    conflicts = [f'同一原图 {file.name}' for file in sorted(train_images & test_images)]
    conflicts += [f'同一文件 {file.name}' for file in sorted((train & test) - (train_images & test_images))]
    for file in sorted(train_content - test):
        conflicts.extend(f'文件内容一致 {file.name} 与 {other.name}'
                         for other in test_by_digest.get(paths[str(file)], []))
    shared_ids = train_ids & test_ids
    conflicts.extend(f'相同实物编号 {sample_label(value)}' for value in sorted(shared_ids))
    if shared_ids or train_images & test_images:
        independence = 'overlap'
    elif config.split_manifest and config.split_manifest.one_image_one_sample and train_images and test_images:
        independence = 'declared_one_image_one_sample'
    else:
        independence = 'known_ids_disjoint' if train_known and test_known else 'unknown'
    return paths, {'status':'preflight', 'conflicts':conflicts, 'duplicate_test_spectra':None,
                   'physical_sample_independence':independence}


def enforce_split(test_usage, checks):
    if test_usage == 'independent_test' and checks['conflicts']:
        raise DataError('EXPERIMENT_SPLIT_OVERLAP', split_check_text(checks) +
                        '\n请修正训练／测试划分，或改作开发复现核验。')


def split_check_text(checks, *, show_conflicts=True):
    if not checks or checks.get('status') in {'skipped','unavailable'}:
        return '划分核验：历史结果未记录重叠核验，重复光谱数量和实物独立性未知。'
    phase = '已核对文件、原图和已知实物编号' if checks['status'] == 'preflight' else '已完成文件、原图、实物编号和光谱核验'
    duplicate = checks['duplicate_test_spectra']
    spectra = ('精确重复光谱将在准备数据后统计' if duplicate is None else
               f'测试侧有 {duplicate} 条光谱与训练侧精确相同（共 {checks["test_spectra"]} 条测试光谱）')
    independence = {'unknown':'实物独立性未知', 'known_ids_disjoint':'已提供的实物编号无交叉',
                    'declared_one_image_one_sample':'按用户声明每图独立实物无交叉',
                    'overlap':'发现相同原图或实物编号'}[checks['physical_sample_independence']]
    conflicts = checks['conflicts']
    detail = f'发现 {len(conflicts)} 项冲突' if conflicts else '未发现文件、原图或已知实物编号交叉'
    if conflicts and show_conflicts:
        detail += '\n' + '\n'.join('• '+item for item in conflicts[:12])
    return f'划分核验：{phase}。{spectra}。{independence}。{detail}'


def check_split(checks, train, test):
    # Compare numerical values, including treating -0.0 and 0.0 as equal.
    def key(row):
        values = np.array(row, dtype='<f8', copy=True)
        values[values == 0] = 0
        return hashlib.sha256(values.tobytes()).digest()

    tokens = {key(row) for row in train.X}
    known_train = {row['sample_id'] for row in train.origins if row.get('sample_id')}
    known_test = {row['sample_id'] for row in test.origins if row.get('sample_id')}
    shared = known_train & known_test
    conflicts = list(checks['conflicts'])
    conflicts.extend(item for value in sorted(shared) if (item := f'相同实物编号 {sample_label(value)}') not in conflicts)
    return {**checks, 'status':'completed', 'conflicts':conflicts,
            'physical_sample_independence':'overlap' if shared else checks['physical_sample_independence'],
            'duplicate_test_spectra':sum(key(row) in tokens for row in test.X), 'test_spectra':len(test.X)}


def independent_duplicate_warning(test_usage, checks):
    repeats = (checks or {}).get('duplicate_test_spectra') or 0
    if test_usage == 'independent_test' and repeats > 0:
        return f'独立测试中存在与训练侧精确相同的光谱（{repeats} 条）。请核查同源数据后再解读独立测试成绩。'
    return None
