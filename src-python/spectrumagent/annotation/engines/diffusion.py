"""TASK-04 §5.3/R10 + user's R18: original-spectrum candidate diffusion.

Growth uses adjacent-pair cos_uv; reporting uses seed-reference cos_s.
This module produces regions only. SessionStore owns the sole candidate queue,
manual labels, consumption, undo and parameter-change behavior.
"""
import base64
from collections import deque
from copy import deepcopy
from io import BytesIO
import math
from numbers import Integral, Real
from time import perf_counter

import numpy as np
from PIL import Image

from spectrumagent.data import DataError
from .superpixels import memory_bytes


# Adjustable DEFAULT, not a business hard constraint: requirements scenario S1,
# line 417 (TASK-04 §5.3). This value governs adjacent-pair growth only.
DEFAULT_THRESHOLD = 0.92
# Adjustable UI-level DEFAULT: ui-v2.3 S05 footnote line 1711 (TASK-04 §5.3).
# This separate guard governs seed-reference minimum similarity, not growth.
DEFAULT_QUEUE_MIN_SIMILARITY = 0.80


def invalid_prompt(message):
    return DataError("INVALID_DIFFUSION_PROMPT", "分割提示不合法",
                     fields=[{"field": "seed", "message": message}])


def _integer(value):
    return isinstance(value, Integral) and not isinstance(value, (bool, np.bool_))


def _point(value, shape):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(_integer(item) for item in value)):
        raise invalid_prompt("坐标须为整数 [line,sample]")
    row, col = map(int, value)
    if not (0 <= row < shape[0] and 0 <= col < shape[1]):
        raise invalid_prompt("提示坐标超出图像范围")
    return row, col


def bresenham(start, end):
    """R18: one-pixel-wide integer line, including both supplied endpoints."""
    row, col = start
    end_row, end_col = end
    dx, dy = abs(end_col-col), -abs(end_row-row)
    sx = 1 if col < end_col else -1
    sy = 1 if row < end_row else -1
    error = dx + dy
    while True:
        yield row, col
        if (row, col) == (end_row, end_col):
            return
        twice = 2 * error
        if twice >= dy:
            error += dy
            col += sx
        if twice <= dx:
            error += dx
            row += sy


def prompt_superpixels(segments, seed):
    """Resolve a single prompt to a unique initial superpixel union (R18)."""
    if not isinstance(seed, dict) or len(seed) != 1:
        raise invalid_prompt("每次须提供一种提示，不得混用")
    kind, value = next(iter(seed.items()))
    if kind == "point":
        return [int(segments[_point(value, segments.shape)])]
    if kind == "box":
        if (not isinstance(value, (list, tuple)) or len(value) != 4
                or not all(_integer(item) for item in value)):
            raise invalid_prompt("框选须为整数 [l0,l1,s0,s1]")
        l0, l1, s0, s1 = map(int, value)
        if not (0 <= l0 < l1 <= segments.shape[0] and 0 <= s0 < s1 <= segments.shape[1]):
            raise invalid_prompt("框选须为图内非空半开区间")
        return np.unique(segments[l0:l1, s0:s1]).astype(int).tolist()
    if kind in ("pixels", "doodle"):
        if not isinstance(value, (list, tuple)) or not value:
            raise invalid_prompt("像素集合/涂鸦须非空")
        points = [_point(item, segments.shape) for item in value]
        ids = {int(segments[point]) for point in points}
        if kind == "doodle":
            for start, end in zip(points, points[1:]):
                ids.update(int(segments[point]) for point in bresenham(start, end))
        return sorted(ids)
    if kind == "superpixels":
        if (not isinstance(value, (list, tuple)) or not value
                or not all(_integer(item) for item in value)
                or not set(value).issubset(np.unique(segments))):
            raise invalid_prompt("超像素集合须非空且 id 存在")
        return sorted({int(item) for item in value})
    raise invalid_prompt("提示须为 point/box/doodle/pixels/superpixels")


def adjacency_edges(segments):
    """R18: unique undirected FOUR-neighbour pairs, no corner contacts."""
    pairs = []
    for left, right in ((segments[:-1], segments[1:]), (segments[:, :-1], segments[:, 1:])):
        crossing = left != right
        pairs.append(np.sort(np.column_stack((left[crossing], right[crossing])), axis=1))
    return np.unique(np.concatenate(pairs), axis=0)


def _threshold(value, field):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, Real)
            or not np.isfinite(value) or not -1 <= value <= 1):
        raise DataError("INVALID_DIFFUSION_PARAMETERS", "余弦阈值须为 [-1,1] 有限数",
                        fields=[{"field": field, "message": "须为 [-1,1] 有限数"}])


def candidate_overlay(segmentation, members):
    """Display-only PCA background; spectral calculations never use features."""
    segments = segmentation.segments
    stride = max(1, math.ceil(max(segments.shape) / 512))  # TASK-04 output limit.
    selected = np.isin(segments[::stride, ::stride], members)
    gray = (segmentation.features.normalized[::stride, ::stride, 0]
            * np.iinfo(np.uint8).max).astype(np.uint8)
    gray[selected] = np.iinfo(np.uint8).max  # White candidate region, no label color.
    image = Image.fromarray(gray).convert("RGB")
    output = BytesIO()
    image.save(output, format="PNG")
    return {"width": image.width, "height": image.height,
            "png_base64": base64.b64encode(output.getvalue()).decode("ascii")}


def grow(segmentation, seed, *, threshold=DEFAULT_THRESHOLD):
    """One prompt -> one candidate, before the independent queue guard.

    Mean spectra come directly from Segmentation.mean_spectra (original bands).
    R18 composite seed: all pixels of the hit superpixels have equal weight.
    R18 seed-member cos_s is DEFINED as 1, including heterogeneous seed unions.
    """
    _threshold(threshold, "threshold")
    segments, means = segmentation.segments, segmentation.mean_spectra
    seeds = prompt_superpixels(segments, seed)
    counts = np.bincount(segments.ravel(), minlength=len(means))
    seed_mean = np.average(means[seeds], axis=0, weights=counts[seeds])
    norms = np.linalg.norm(means, axis=1)
    seed_norm = np.linalg.norm(seed_mean)
    if np.any(norms == 0) or seed_norm == 0:
        raise DataError("UNDEFINED_COSINE", "零范数原谱均值无法计算余弦")
    unit = means / norms[:, None]
    edges = adjacency_edges(segments)
    cos_uv = np.clip(np.einsum("ij,ij->i", unit[edges[:, 0]], unit[edges[:, 1]]), -1, 1)
    neighbours = [[] for _ in means]
    for (left, right), similarity in zip(edges, cos_uv):
        if similarity >= threshold:
            neighbours[left].append(int(right))
            neighbours[right].append(int(left))
    included = np.zeros(len(means), dtype=bool)
    included[seeds] = True
    pending = deque(seeds)
    while pending:
        for neighbour in neighbours[pending.popleft()]:
            if not included[neighbour]:
                included[neighbour] = True
                pending.append(neighbour)
    cos_s = np.clip(unit @ (seed_mean / seed_norm), -1, 1)
    cos_s[seeds] = 1  # R18 definition, never used for growth.
    members = np.flatnonzero(included).tolist()
    return {"superpixels": members, "pixel_count": int(counts[included].sum()),
            "seed_superpixels": seeds, "min_similarity": float(cos_s[included].min()),
            "avg_similarity": float(cos_s[included].mean()), "cos_s": cos_s.tolist(),
            "overlay": candidate_overlay(segmentation, members)}


class DiffusionEngine:
    """Production seam only: reuse superpixel cache and SessionStore queue.

    Does not generate superpixels implicitly or own a second candidate queue.
    Both existing locks cover the cache -> working-state -> enqueue operation.
    """
    def __init__(self, superpixels, sessions):
        self.superpixels, self.sessions = superpixels, sessions

    def generate(self, cube_id, seed, *, threshold=DEFAULT_THRESHOLD,
                 queue_min_similarity=DEFAULT_QUEUE_MIN_SIMILARITY):
        _threshold(threshold, "threshold")
        _threshold(queue_min_similarity, "queue_min_similarity")
        cube_id = str(cube_id)
        with self.superpixels.lock, self.sessions._lock:
            started = perf_counter()
            # Revalidate even though spectra are already resident; SOURCE_CHANGED
            # wrapping belongs exclusively to Registry.readable (R14).
            dataset, _ = self.superpixels.registry.readable(cube_id, raw=False)
            del dataset
            cached = self.superpixels.cache.get(cube_id)
            if cached is None:
                raise DataError("SUPERPIXELS_REQUIRED", "请先生成超像素分割")
            segmentation = cached[1]
            candidate = grow(segmentation, seed, threshold=threshold)
            self.sessions.set_segmentation(cube_id, segmentation)
            state = self.sessions._state(cube_id)
            admitted = candidate["min_similarity"] >= queue_min_similarity
            if admitted:
                state.candidates.append(deepcopy(candidate))
            return {"candidate": candidate, "candidates": deepcopy(state.candidates),
                    "enqueued": bool(admitted),
                    "not_queued_reasons": {"below_queue_min_similarity": int(not admitted)},
                    "params": {"threshold": threshold, "queue_min_similarity": queue_min_similarity},
                    "feature_bytes": segmentation.features.normalized.nbytes,
                    "mean_spectra_bytes": segmentation.mean_spectra.nbytes,
                    "peak_rss_bytes": memory_bytes()[1],
                    "elapsed_seconds": perf_counter() - started}
