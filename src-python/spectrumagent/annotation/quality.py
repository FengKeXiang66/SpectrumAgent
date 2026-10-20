"""Current-state spectral checks, TASK-04 §5.5/R17; no model assertions."""
import numpy as np

from spectrumagent.data import DataError
from .engines.superpixels import ReadableRows, spectral_statistics
from .session import aggregate_spectra, map_statistics


# Implementation default, adjustable; R17-authorized SYNTHETIC calibration on
# pe/20260804205214_64, m=.5, KMeans(4, random_state=0, n_init=10), empirical p05.
# Source: milestone04/evidence/10.3/quality-calibration.json. Not human-label quality.
DEFAULT_COSINE_THRESHOLD = 0.8579512304124653


def cosine(left, right):
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0:
        raise DataError("UNDEFINED_COSINE", "零范数原谱均值无法计算余弦")
    return float(np.clip(np.dot(left, right) / denominator, -1, 1))


def validate(registry, cube_id, label_map, segments, label_ids, params, *, threshold=None, aggregates=None):
    threshold = DEFAULT_COSINE_THRESHOLD if threshold is None else threshold
    if threshold is None or not np.isfinite(threshold) or not -1 <= threshold <= 1:
        raise DataError("INVALID_QUALITY_THRESHOLD", "余弦阈值须在 [-1,1]")
    if np.any(label_map >= len(label_ids)):
        raise DataError("INVALID_LABEL_MAP", "label_index 超出项目映射")
    if aggregates is None:
        aggregates = aggregate_spectra(registry, cube_id, label_map,
                                       block_size=params["block_size"], segments=segments)
    comparisons = []
    for (segment, label), moments in sorted(aggregates.parts.items()):
        comparisons.append({"superpixel_id": segment, "label_index": label,
                            "pixel_count": moments.count,
                            "cos": cosine(moments.mean, aggregates.labels[label].mean)})
    suspicious = [item for item in comparisons if item["cos"] < threshold]
    dataset, _ = registry.readable(cube_id, raw=False)
    shape = dataset.shape
    del dataset
    counts, _, std = spectral_statistics(ReadableRows(registry, cube_id, shape), segments, params["block_size"])
    d_s = std.mean(axis=1)
    tau = float(params["k"] * np.median(d_s))
    return {"threshold": float(threshold), "threshold_level": "实现层默认、可调",
            "reference": "当前工作态原谱反射率均值；(超像素∩label) vs label",
            "suspicious": suspicious, "comparisons": comparisons,
            "high_variance": {"d_s": d_s.tolist(), "tau": tau,
                              "superpixel_ids": np.flatnonzero((d_s > tau) & (counts >= 8)).tolist()},
            "completeness": map_statistics(label_map, label_ids),
            "not_applicable": {"标签与聚类中心冲突": "无模型阶段不适用",
                               "类间重叠": "无模型阶段不适用"}}
