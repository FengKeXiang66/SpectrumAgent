"""R17-authorized SYNTHETIC threshold behavior, never human-label quality.

Standalone: python src-python/tests/annotation/calibrate_quality.py --output <E: path>
No source writes, snapshots, annotation rows, or fixed-seed manifest changes.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src-python"))

import numpy as np
from sklearn.cluster import KMeans

from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.annotation.engines.superpixels import Parameters, SuperpixelEngine, memory_bytes
from spectrumagent.annotation.quality import cosine, validate


def calibrate(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    registry = DatasetRegistry(ROOT / ".runtime" / "m04-quality-calibration" / "registry.sqlite3")
    header = (ROOT / "milestone04/evidence/calibration/cubes_11.txt").read_text("utf-8").splitlines()[0]
    cube_id = registry.import_path(header).datasets[0].id
    result = SuperpixelEngine(registry).generate(cube_id, Parameters(compactness=0.5))
    synthetic = KMeans(n_clusters=4, random_state=0, n_init=10).fit_predict(result.mean_spectra)
    label_map = synthetic[result.segments].astype(np.int32)
    ids = tuple(f"SYNTHETIC_CLUSTER_{i}" for i in range(4))
    start = perf_counter()
    baseline = validate(registry, cube_id, label_map, result.segments, ids,
                        result.report["params"], threshold=-1)
    distribution = np.array([item["cos"] for item in baseline["comparisons"]])
    # Implementation-level selection rule: empirical p05, not a business limit.
    threshold = float(np.quantile(distribution, 0.05))
    triggered = int(np.count_nonzero(distribution < threshold))
    assert 0 < triggered < len(distribution)
    # Deliberately put one block into its least-similar OTHER synthetic group.
    from spectrumagent.annotation.session import aggregate_spectra
    moments = aggregate_spectra(registry, cube_id, label_map)
    choices = [(cosine(mean, moments.labels[label].mean), segment, label)
               for segment, mean in enumerate(result.mean_spectra)
               for label in range(4) if label != synthetic[segment]]
    _, implanted_segment, implanted_label = min(choices)
    implanted_map = label_map.copy()
    implanted_map[result.segments == implanted_segment] = implanted_label
    implanted = validate(registry, cube_id, implanted_map, result.segments, ids,
                         result.report["params"], threshold=threshold)
    detected = any(item["superpixel_id"] == implanted_segment and item["label_index"] == implanted_label
                   for item in implanted["suspicious"])
    assert detected
    report = {"purpose": "R17 合成标注阈值行为与植入离群验证；不是人工标注，不是标注质量断言",
              "source_level": "实现层实测；默认可调", "header": header,
              "shape": result.report["shape"], "params": asdict(Parameters()),
              "clustering": {"n_clusters": 4, "random_state": 0, "n_init": 10},
              "superpixel_count": len(result.mean_spectra),
              "reference": "原谱反射率；块均值 vs 当前合成 label 的像素加权均值",
              "quantiles": {str(q): float(np.quantile(distribution, q))
                            for q in (0, .01, .05, .25, .5, .75, .95, .99, 1)},
              "selection": "实测 cos 的 p05（实现层选择，非硬约束）",
              "default_threshold": threshold, "comparisons": len(distribution),
              "triggered": triggered, "trigger_fraction": triggered / len(distribution),
              "implant": {"superpixel_id": implanted_segment, "label_index": implanted_label,
                          "detected": detected}, "validation_seconds": perf_counter() - start,
              "feature_bytes": result.report["feature_bytes"], "peak_rss_bytes": memory_bytes()[1]}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    calibrate(parser.parse_args().output)
