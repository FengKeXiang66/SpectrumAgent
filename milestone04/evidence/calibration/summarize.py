"""Audit the complete authorized grid and derive a reproducible measured summary."""
import csv
import hashlib
import importlib.metadata
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]


def main():
    rows = list(csv.DictReader((ROOT / "compactness.csv").open(encoding="utf-8", newline="")))
    manifest = (ROOT / "cubes_11.txt").read_text("utf-8").splitlines()
    assert len(rows) == 55 and len(manifest) == 11
    assert len({(row["cube"], float(row["compactness"])) for row in rows}) == 55
    assert {float(row["compactness"]) for row in rows} == {.2, .5, 1., 2., 10.}
    cubes = sorted({row["cube"] for row in rows})
    assert len(cubes) == 11
    assert {category: sum(cube.startswith(category + "/") for cube in cubes) for category in ("pe", "pet", "pp")} == {"pe": 3, "pet": 4, "pp": 4}
    for row in rows:
        assert (int(row["n_segments"]), int(row["pca_components"]), int(row["k"]), int(row["block_size"])) == (800, 5, 3, 32)
        assert row["convert2lab"] == "False" and row["enforce_connectivity"] == "True"
        assert int(row["feature_bytes"]) == 231*640*5*4
        assert int(row["n_after"]) >= int(row["n"])
    groups = {}
    for compactness in (.2, .5, 1., 2., 10.):
        group = [row for row in rows if float(row["compactness"]) == compactness]
        assert len(group) == 11
        def bounds(field, conversion=float):
            values = [conversion(row[field]) for row in group]
            return [min(values), max(values)]
        groups[str(compactness)] = {
            "cubes": len(group),
            # Existing §6.1 assertions, not thresholds invented for selection.
            "all_structure_assertions_pass": sum(689 <= int(row["n"]) <= 842 and float(row["area_cv"]) >= .10 and float(row["R"]) >= 1.5 and int(row["subdivision_triggers"]) >= 1 for row in group),
            "n_range": bounds("n", int), "area_cv_range": bounds("area_cv"), "R_range": bounds("R"),
            "subdivision_triggers_range": bounds("subdivision_triggers", int), "n_after_range": bounds("n_after", int),
        }
    chosen = groups["0.5"]
    # Keep the existing default only if every cube meets the card's assertions.
    if chosen["all_structure_assertions_pass"] != 11:
        raise RuntimeError("0.5 is not universally valid; inspect all measured rows before selecting/backfilling")
    baseline = next(row for row in rows if row["cube"] == "pe/20260804205214_64.hdr" and float(row["compactness"]) == .5)
    raw_float64_bytes = 231*640*200*8
    peak_deltas = [int(row["peak_rss_delta_bytes"]) for row in rows]
    summary = {
        "grid_rows": len(rows), "cube_count": len(cubes), "selected_compactness": .5,
        "selection_basis": "11/11 cubes pass existing §6.1 n/area_cv/R/subdivision assertions at the current default",
        "by_compactness": groups, "baseline": baseline,
        "feature_bytes": 231*640*5*4,
        "raw_float64_cube_bytes": raw_float64_bytes,
        "peak_rss_bytes_range": [min(int(row["peak_rss_bytes"]) for row in rows), max(int(row["peak_rss_bytes"]) for row in rows)],
        "peak_rss_delta_bytes_range": [min(peak_deltas), max(peak_deltas)],
        "worst_peak_delta_fraction_of_raw_float64_cube": max(peak_deltas)/raw_float64_bytes,
        "total_seconds_range": [min(float(row["total_seconds"]) for row in rows), max(float(row["total_seconds"]) for row in rows)],
        "versions": {name: importlib.metadata.version(name) for name in ("numpy", "scikit-image", "scikit-learn", "spectral")},
        "source_commit": "fa44fe8af3ef0374154a91a539b3d98b6af02412",
        "seed_sha256": hashlib.sha256((REPO / "milestone04/evidence/seeds_20.json").read_bytes()).hexdigest(),
    }
    (ROOT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2)+"\n", "utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
