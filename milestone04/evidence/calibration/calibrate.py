"""Independent rerunnable 11-cube / five-compactness calibration (TASK-04 §10.2).

Run from any cwd: E:/AI_Agent/.venv/Scripts/python.exe <this script>
All temporary files and the separate registry live on E: by default.
Each cell runs in a fresh child for interpretable OS peak-RSS measurements.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME = REPO / ".runtime" / "m04-recheck" / "calibration"
DEFAULT_OUTPUT = Path(__file__).resolve().parent
COMPACTNESSES = (0.2, 0.5, 1, 2, 10)  # 10.2 execution order, user-authorized grid.


def independent_ratio(zscore5, segments):
    """PCA-5 z-score / four-neighbour / squared Euclidean MEAN ratio.

    Independent implementation: explicit rows, no engine metric helper.
    Keep sums AND pair counts to diagnose an accidental ratio-of-sums.
    """
    import numpy as np
    assert zscore5.shape[2] == 5
    inside_sum = outside_sum = 0.0
    inside_count = outside_count = 0
    for row in range(segments.shape[0]):
        pairs = [(zscore5[row, :-1], zscore5[row, 1:], segments[row, :-1] != segments[row, 1:])]
        if row + 1 < segments.shape[0]:
            pairs.append((zscore5[row], zscore5[row+1], segments[row] != segments[row+1]))
        for a, b, crosses in pairs:
            distance = ((a.astype(np.float64) - b.astype(np.float64)) ** 2).sum(axis=-1)
            outside_sum += float(distance[crosses].sum())
            inside_sum += float(distance[~crosses].sum())
            outside_count += int(crosses.sum())
            inside_count += int((~crosses).sum())
    return (outside_sum/outside_count)/(inside_sum/inside_count), outside_sum/inside_sum


def worker(args):
    import numpy as np
    from spectrumagent.api.registry import DatasetRegistry
    from spectrumagent.annotation.engines.superpixels import Parameters, SuperpixelEngine
    registry = DatasetRegistry(args.runtime / "registry.sqlite3")
    result = SuperpixelEngine(registry).generate(args.cube_id, Parameters(compactness=args.m, pca_components=args.components))
    report = result.report
    ratio, sum_ratio = independent_ratio(result.reference_zscore5, result.initial_segments)
    if not np.isclose(ratio, report["R"], rtol=1e-12, atol=1e-12):
        raise AssertionError(f"Independent R mismatch: {ratio} != {report['R']}")
    row = {"cube": args.cube_name, "compactness": args.m, "n": report["n_before"],
           "area_cv": report["area_cv"], "R": ratio, "sum_ratio_diagnostic": sum_ratio,
           "subdivision_triggers": len(report["subdivided_ids"]), "n_after": report["n_after"],
           "tau": report["tau"], "n_segments": report["params"]["n_segments"],
           "pca_components": report["params"]["pca_components"], "k": report["params"]["k"],
           "block_size": report["params"]["block_size"], "feature_version": report["params"]["feature_version"],
           "convert2lab": False, "enforce_connectivity": True,
           "feature_bytes": report["feature_bytes"], "resident_feature_bytes": report["resident_feature_bytes"],
           "baseline_rss_bytes": report["baseline_rss_bytes"], "peak_rss_bytes": report["peak_rss_bytes"],
           "peak_rss_delta_bytes": report["peak_rss_delta_bytes"],
           "pca_seconds": report["pca_seconds"], "slic_seconds": report["slic_seconds"], "total_seconds": report["total_seconds"]}
    print(json.dumps(row, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("E:/高光谱数据集/plastic"))
    parser.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--cube-id")
    parser.add_argument("--cube-name")
    parser.add_argument("--m", type=float)
    parser.add_argument("--components", type=int, default=5)
    args = parser.parse_args()
    if args.runtime.resolve().drive.upper() != "E:":
        parser.error("temporary runtime must reside on E:")
    args.runtime.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(args.runtime.resolve())
    tempfile.tempdir = str(args.runtime.resolve())
    sys.path[:0] = [str(REPO), str(REPO / "src-python")]
    if args.worker:
        worker(args)
        return
    from spectrumagent.api.registry import DatasetRegistry
    registry = DatasetRegistry(args.runtime / "registry.sqlite3")
    headers = sorted(args.data_root.rglob("*.hdr"))
    if len(headers) != 11 or {category: sum(p.parent.name == category for p in headers) for category in ("pe", "pet", "pp")} != {"pe": 3, "pet": 4, "pp": 4}:
        raise RuntimeError("Expected all 11 cubes: pe3/pet4/pp4")
    (args.output / "cubes_11.txt").write_text("\n".join(str(p.resolve()) for p in headers)+"\n", "utf-8")
    records = [(header, registry.import_path(str(header)).datasets[0].id) for header in headers]
    output = args.output / "compactness.csv"
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = None
        for header, identifier in records:
            for m in COMPACTNESSES:
                name = header.relative_to(args.data_root).as_posix()
                command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--runtime", str(args.runtime),
                           "--output", str(args.output), "--cube-id", str(identifier), "--cube-name", name,
                           "--m", str(m), "--components", str(args.components)]
                completed = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8",
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                # Registry may log unknown ENVI keys on stdout before the final JSON row.
                row = json.loads(completed.stdout.strip().splitlines()[-1])
                if writer is None:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    writer.writeheader()
                writer.writerow(row)
                stream.flush()
                print(f"{name} m={m}: n={row['n']} cv={row['area_cv']:.6f} R={row['R']:.6f} split={row['subdivision_triggers']} -> {row['n_after']} peak_delta={row['peak_rss_delta_bytes']}B", flush=True)
    print(f"Saved 55 measured rows: {output}", flush=True)


if __name__ == "__main__":
    main()
