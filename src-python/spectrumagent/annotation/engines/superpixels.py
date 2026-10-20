"""TASK-04 §5.2: bounded original spectra, resident PCA maps, SLIC/refinement.

Defaults: task §5.2 (implementation-level defaults, not business hard limits).
R: task §6.1, PCA-5 z-score, four-neighbours, squared Euclidean MEAN ratio.
"""
import base64
from dataclasses import asdict, dataclass
import ctypes
from ctypes import wintypes
from io import BytesIO
import math
from threading import RLock
from time import perf_counter

import numpy as np
from PIL import Image, ImageDraw
from sklearn.decomposition import IncrementalPCA
from skimage.segmentation import slic

from spectrumagent.data import DataError


FEATURE_VERSION = "pca-global-zscore-clip3-unit-v1"
DEFAULT_COMPACTNESS = 0.5  # §5.2 single-cube initial default; calibration decides.


@dataclass(frozen=True)
class Parameters:
    n_segments: int = 800
    compactness: float = DEFAULT_COMPACTNESS
    pca_components: int = 5
    k: float = 3
    block_size: int = 32
    feature_version: str = FEATURE_VERSION


class ProcessMemory(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def memory_bytes():
    """Windows RSS and OS-recorded process peak; bytes, no new dependency."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = ProcessMemory()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)


def row_blocks(dataset, block_size):
    for l0 in range(0, dataset.shape[0], block_size):
        l1 = min(l0 + block_size, dataset.shape[0])
        block = dataset.read_region(l0, l1, 0, dataset.shape[1])
        if not np.isfinite(block).all():
            raise DataError("NON_FINITE_SPECTRA", "超像素输入包含非有限光谱值")
        yield l0, l1, block
        del block  # Release the yielded read buffer BEFORE allocating the next one.


@dataclass
class Features:
    normalized: np.ndarray
    zscore: np.ndarray
    mean: np.ndarray
    std: np.ndarray
    pca: IncrementalPCA


class ReadableRows:
    """Keep source mappings scoped to one read; mapped pages are not a cube cache.

    Only public Registry.readable/read_region are used. Each block is revalidated,
    and releasing its dataset closes that block's read-only memmap naturally.
    """
    def __init__(self, registry, cube_id, shape):
        self.registry, self.cube_id, self.shape = registry, cube_id, shape

    def read_region(self, l0, l1, s0, s1):
        dataset, _ = self.registry.readable(self.cube_id, raw=False)
        return dataset.read_region(l0, l1, s0, s1)


def pca_features(dataset, components, block_size):
    """Two independent disk passes; original blocks are never retained."""
    lines, samples, bands = dataset.shape
    tail_samples = (lines % block_size or min(lines, block_size)) * samples
    if components > min(bands, min(lines, block_size) * samples, tail_samples):
        raise DataError("INVALID_SUPERPIXEL_PARAMETERS", "PCA 分量数不得超过波段数或任一行块样本数")
    # Each read buffer is disposable: IPCA may center it in place; no second copy.
    # This changes buffer ownership only, never batch boundaries or PCA arithmetic.
    pca = IncrementalPCA(n_components=components, batch_size=block_size * samples, copy=False)
    for _, _, block in row_blocks(dataset, block_size):
        pca.partial_fit(block.reshape(-1, bands))
        del block
    feature = np.empty((lines, samples, components), dtype=np.float32)
    for l0, l1, block in row_blocks(dataset, block_size):
        feature[l0:l1] = pca.transform(block.reshape(-1, bands)).reshape(l1-l0, samples, components)
        del block
    # R4: measure the FILLED resident float32 map, not explained_variance_.
    mean, std = np.empty(components), np.empty(components)
    for component in range(components):
        view = feature[:, :, component]
        mean[component] = view.mean(dtype=np.float64)
        std[component] = view.std(dtype=np.float64)
        view -= mean[component]
        if std[component] == 0:
            view.fill(0)
        else:
            view /= std[component]
    zscore = feature.copy()  # PCA feature map allowed by §11.4; R uses PRE-clip z-score.
    np.clip(feature, -3, 3, out=feature)
    feature += 3
    feature /= 6
    return Features(feature, zscore, mean, std, pca)


def spectral_statistics(dataset, segments, block_size):
    """Original reflectance, accumulated sum/sumsq/count, bounded row reads."""
    count_segments = int(segments.max()) + 1
    bands = dataset.shape[2]
    sums = np.zeros((count_segments, bands), dtype=np.float64)
    squares = np.zeros_like(sums)
    counts = np.zeros(count_segments, dtype=np.int64)
    for l0, l1, block in row_blocks(dataset, block_size):
        ids = segments[l0:l1].ravel()
        spectra = block.reshape(-1, bands)
        counts += np.bincount(ids, minlength=count_segments)
        for band in range(bands):
            values = spectra[:, band]
            sums[:, band] += np.bincount(ids, weights=values, minlength=count_segments)
            squares[:, band] += np.bincount(ids, weights=values * values, minlength=count_segments)
        del values, spectra, block
    means = sums / counts[:, None]
    variance = squares / counts[:, None] - means * means
    np.maximum(variance, 0, out=variance)
    np.sqrt(variance, out=variance)
    return counts, means, variance


def boundary_ratio(zscore5, segments):
    """§6.1: PCA-5 z-score / 4-neighbour / squared Euclidean MEAN ratio.

    Each undirected horizontal/vertical pair counted once; never ratio of sums.
    """
    if zscore5.shape[2] != 5:
        raise ValueError("R requires the PCA-5 reference map")
    sums = [0.0, 0.0]
    counts = [0, 0]
    for axis in (0, 1):
        left, right = (slice(None, -1), slice(1, None))
        a = (left, slice(None)) if axis == 0 else (slice(None), left)
        b = (right, slice(None)) if axis == 0 else (slice(None), right)
        distances = np.sum((zscore5[a].astype(np.float64) - zscore5[b]) ** 2, axis=2)
        crossing = segments[a] != segments[b]
        for i, mask in enumerate((~crossing, crossing)):
            sums[i] += float(distances[mask].sum(dtype=np.float64))
            counts[i] += int(np.count_nonzero(mask))
    ratio = None if not all(counts) or sums[0] == 0 else (sums[1] / counts[1]) / (sums[0] / counts[0])
    return {"R": ratio, "internal_sum": sums[0], "boundary_sum": sums[1],
            "internal_pairs": counts[0], "boundary_pairs": counts[1],
            "sum_ratio_diagnostic": None if sums[0] == 0 else sums[1] / sums[0]}


def slic_map(feature, n_segments, compactness):
    return slic(feature, n_segments=n_segments, compactness=compactness,
                channel_axis=2, convert2lab=False, start_label=0,
                enforce_connectivity=True).astype(np.int32, copy=False)


def refine(feature, original, counts, d_s, tau, params):
    segments = original.copy()
    triggers = np.flatnonzero((d_s > tau) & (counts >= 8))  # §5.2 fragmentation floor.
    next_id = int(original.max()) + 1
    children = {}
    target_half = original.size / params.n_segments / 2
    for parent in triggers:
        rows, cols = np.nonzero(original == parent)
        l0, l1, s0, s1 = rows.min(), rows.max()+1, cols.min(), cols.max()+1
        owner = original[l0:l1, s0:s1] == parent
        n_sub = max(2, round(int(counts[parent]) / target_half))
        local = slic_map(feature[l0:l1, s0:s1], n_sub, params.compactness)
        new_ids = []
        for index, local_id in enumerate(np.unique(local[owner])):
            mask = owner & (local == local_id)
            # Reuse the parent id for its first child. No renumbering can touch
            # any neighbour pixel, including neighbours inside this bbox.
            child = int(parent) if index == 0 else next_id
            segments[l0:l1, s0:s1][mask] = child
            new_ids.append(child)
            if index != 0:
                next_id += 1
        children[int(parent)] = new_ids
    return segments, triggers.tolist(), children


def overlay_png(feature, segments):
    stride = max(1, math.ceil(max(segments.shape) / 512))  # §5.2 output side limit.
    reduced = segments[::stride, ::stride]
    gray = (feature[::stride, ::stride, 0] * np.iinfo(np.uint8).max).astype(np.uint8)
    image = Image.fromarray(gray).convert("RGB")
    boundary = np.zeros(reduced.shape, dtype=bool)
    boundary[1:] |= reduced[1:] != reduced[:-1]
    boundary[:, 1:] |= reduced[:, 1:] != reduced[:, :-1]
    pixels = np.asarray(image).copy()
    pixels[boundary] = np.iinfo(np.uint8).max
    image = Image.fromarray(pixels)
    draw = ImageDraw.Draw(image)
    for identifier in np.unique(reduced):
        rows, cols = np.nonzero(reduced == identifier)
        draw.text((float(cols.mean()), float(rows.mean())), str(identifier), fill="white", anchor="mm")
    output = BytesIO()
    image.save(output, format="PNG")
    return {"width": image.width, "height": image.height,
            "png_base64": base64.b64encode(output.getvalue()).decode("ascii")}


@dataclass
class Segmentation:
    segments: np.ndarray
    initial_segments: np.ndarray
    mean_spectra: np.ndarray
    std_spectra: np.ndarray
    features: Features
    reference_zscore5: np.ndarray
    report: dict


class SuperpixelEngine:
    def __init__(self, registry):
        self.registry = registry
        self.lock = RLock()
        self.cache = {}

    def generate(self, cube_id, params=Parameters(), *, force=False):
        with self.lock:
            # Revalidate even on a cache hit; force=False must never hide SOURCE_CHANGED.
            dataset, _ = self.registry.readable(cube_id, raw=False)
            key = str(cube_id)
            if not force and key in self.cache and self.cache[key][0] == params:
                return self.cache[key][1]
            if (type(params.n_segments) is not int or params.n_segments < 1
                    or type(params.block_size) is not int or params.block_size < 1
                    or type(params.pca_components) is not int or params.pca_components < 1
                    or not np.isfinite(params.compactness) or params.compactness <= 0
                    or not np.isfinite(params.k) or params.k <= 0):
                raise DataError("INVALID_SUPERPIXEL_PARAMETERS", "超像素参数必须为有限正数，计数必须为正整数")
            baseline_rss, baseline_peak = memory_bytes()
            start = perf_counter()
            dataset = ReadableRows(self.registry, cube_id, dataset.shape)
            features = pca_features(dataset, params.pca_components, params.block_size)
            if params.pca_components == 5:
                reference = features.zscore
            else:
                reference_features = pca_features(dataset, 5, params.block_size)
                reference = reference_features.zscore
                del reference_features
            pca_seconds = perf_counter() - start
            initial = slic_map(features.normalized, params.n_segments, params.compactness)
            slic_seconds = perf_counter() - start - pca_seconds
            counts, _, std = spectral_statistics(dataset, initial, params.block_size)
            d_s = std.mean(axis=1)
            tau = float(params.k * np.median(d_s))
            segments, triggers, children = refine(features.normalized, initial, counts, d_s, tau, params)
            _, means, std = spectral_statistics(dataset, segments, params.block_size)
            metrics = boundary_ratio(reference, initial)
            overlay = overlay_png(features.normalized, segments)
            _, peak = memory_bytes()
            report = {"cube_id": key, "shape": list(dataset.shape),
                      "params": {**asdict(params), "pca_batch_size": features.pca.batch_size},
                      "n_before": len(counts), "n_after": len(means), "superpixel_count": len(means),
                      "area_cv": float(counts.std() / counts.mean()), **metrics,
                      "d_s": d_s.tolist(), "tau": tau, "subdivided_ids": triggers,
                      "parent_children": children, "feature_bytes": features.normalized.nbytes,
                      "resident_feature_bytes": features.normalized.nbytes + features.zscore.nbytes + (reference.nbytes if reference is not features.zscore else 0),
                      "feature_mean": features.mean.tolist(), "feature_std": features.std.tolist(),
                      "normalized_mean": features.normalized.mean(axis=(0, 1), dtype=np.float64).tolist(),
                      "normalized_std": features.normalized.std(axis=(0, 1), dtype=np.float64).tolist(),
                      "normalized_min": float(features.normalized.min()), "normalized_max": float(features.normalized.max()),
                      "baseline_rss_bytes": baseline_rss, "baseline_peak_rss_bytes": baseline_peak,
                      "peak_rss_bytes": peak, "peak_rss_delta_bytes": max(0, peak-baseline_rss),
                      "pca_seconds": pca_seconds, "slic_seconds": slic_seconds,
                      "total_seconds": perf_counter()-start, "overlay": overlay}
            result = Segmentation(segments, initial, means, std, features, reference, report)
            self.cache[key] = (params, result)
            return result
