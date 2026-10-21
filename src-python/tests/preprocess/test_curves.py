"""D1: curves come only from the final bounded B01/recipe pass."""
import json

import numpy as np

from .run_fixtures import run_case, step


def source_for(case, steps):
    recipe = case.recipe(steps)
    return case.runner._preflight(case.cube, case.version, recipe, 7, "clip")[1], recipe


def test_collect_before_defaults_false_and_stays_empty(run_case):
    source, _ = source_for(run_case, [step("snv")])
    assert source.collect_before is False
    assert len(list(source.lines())) > 0
    assert source.before == {}


def test_final_pass_collects_b01_class_sums_counts_and_unlabeled(run_case):
    source, recipe = source_for(run_case, [step("snv")])
    source.collect_before = True
    list(source.lines())
    for index, state in source.before.items():
        pixels = run_case.values[run_case.label_map == index].astype(np.float64)/65535
        assert state["count"] == len(pixels)
        np.testing.assert_allclose(state["sum"], pixels.sum(axis=0), atol=1e-14)
    assert set(source.before) == {0, 1, 2}
    blank = np.full_like(source.label_map, -1)
    np.savez_compressed(run_case.paths.snapshots/run_case.cube/"v1"/"label_map.npz", label_map=blank)
    row = run_case.runner.run(run_case.cube, run_case.version, recipe)
    assert row["status"] == "succeeded"
    curves = run_case.report(row)["curves"]
    assert curves["labeled"] is False
    assert [item["label_index"] for item in curves["classes"]] == [-1]
    assert curves["classes"][0]["count"] == blank.size
    expected = run_case.runner.operators.run(run_case.values.reshape(-1, 8)/65535,
                                             {"steps": [step("snv")]}).spectra.mean(axis=0)
    np.testing.assert_allclose(curves["classes"][0]["after"], expected, atol=1e-14)


def test_global_fitting_passes_never_pollute_before(run_case, monkeypatch):
    from spectrumagent.preprocess.run import BoundedInput
    original = BoundedInput.lines
    calls = []
    def observe(source):
        collect = source.collect_before
        if not collect:
            assert source.before == {}
        yield from original(source)
        if not collect:
            assert source.before == {}
        calls.append(collect)
    monkeypatch.setattr(BoundedInput, "lines", observe)
    for op in ("pca", "mnf", "ica"):
        recipe = run_case.recipe([step("standardize", method="standard"), step(op, n_components=2)])
        row = run_case.runner.run(run_case.cube, run_case.version, recipe, block_size=3)
        assert row["status"] == "succeeded", row["error"]
        curves = run_case.report(row)["curves"]
        assert sum(item["count"] for item in curves["classes"]) == 110
        assert curves["wavelengths_out"] is None
    assert calls.count(True) == 3
    assert calls.count(False) > 3


def test_curves_json_axes_sampling_nan_and_class_contract(run_case):
    source = list(np.arange(8, dtype=float))
    recipe = run_case.recipe([step("crop", source=source, range=[1., 6.]),
                              step("resample", source=source[1:7], target=list(np.linspace(1., 6., 600)), method="linear")])
    row = run_case.runner.run(run_case.cube, run_case.version, recipe)
    assert row["status"] == "succeeded"
    report = run_case.report(row)
    curves = report["curves"]
    assert set(curves) == {"labeled", "wavelengths_in", "wavelengths_out", "classes", "sampling"}
    assert curves["wavelengths_in"] is None  # Fixture has no header wavelengths.
    sampled = np.unique(np.round(np.linspace(0, 599, 512)).astype(int))
    np.testing.assert_array_equal(curves["wavelengths_out"], np.linspace(1., 6., 600)[sampled])
    spectra = run_case.spectra(row)
    for item in curves["classes"]:
        index = item["label_index"]
        assert set(item) == {"label_index", "count", "before", "after"}
        assert len(item["before"]) == 8 and len(item["after"]) == 512
        np.testing.assert_allclose(item["before"], (run_case.values[run_case.label_map == index]/65535).mean(axis=0))
        np.testing.assert_array_equal(item["after"], spectra[f"mean_{index}"][sampled])
    # Out-of-range resampling leaves NaN in every spectrum: absent moments => after:null.
    recipe = run_case.recipe([step("resample", source=source, target=[-1., 8.], method="linear")])
    row = run_case.runner.run(run_case.cube, run_case.version, recipe)
    curves = run_case.report(row)["curves"]
    assert all(item["after"] is None for item in curves["classes"])
    json.dumps(curves, allow_nan=False)
    assert "非均值池化" in curves["sampling"]
