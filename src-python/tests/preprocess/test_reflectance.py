"""TASK-05 §5 B01: formulas, hdr-only decisions, guards and unchanged axes."""
import json

import numpy as np
import pytest

from spectrumagent.data import DataError
from .conftest import run


@pytest.mark.parametrize("hdr,x,params,branch,expected", [
    ({"data type": 12, "reflectance scale factor": 100}, [[20,40,60]], {}, "scale", [[.2,.4,.6]]),
    ({"data type": 5}, [[.2,.4,.6]], {}, "passthrough", [[.2,.4,.6]]),
    ({"data type": 12, "white reference": "w.hdr", "dark reference": "d.hdr"}, [[30,50,70]],
     {"white_reference": np.array([110.,110.,110.]), "dark_reference": np.array([10.,10.,10.])}, "reference", [[.2,.4,.6]]),
])
def test_three_hdr_branches_formulas_and_records(registry, hdr, x, params, branch, expected):
    source = np.array(x)
    original = source.copy()
    result = run(registry, "reflectance", source, {"hdr": hdr, **params})
    np.testing.assert_allclose(result.spectra, expected, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(source, original)
    meta = result.steps[0]["meta"]
    assert meta == {"branch": branch, "matched_criteria": [branch], "guard": "clip", "negative_clipped": 0, "nan_bands": 0}
    json.dumps(result.steps, allow_nan=False)


@pytest.mark.parametrize("hdr,x,code,matches", [
    ({"data type": 5, "reflectance scale factor": 100}, [[.2,.4]], "AMBIGUOUS_REFLECTANCE_INPUT", ["scale","passthrough"]),
    ({"data type": 12, "white reference": "w", "dark reference": "d", "reflectance scale factor": 100}, [[20,40]], "AMBIGUOUS_REFLECTANCE_INPUT", ["reference","scale"]),
    ({"data type": 12}, [[20,40]], "UNKNOWN_REFLECTANCE_INPUT", []),
    ({"data type": 5}, [[2.,4.]], "UNKNOWN_REFLECTANCE_INPUT", []),
])
def test_ambiguous_and_unknown_never_guess(registry, hdr, x, code, matches):
    with pytest.raises(DataError) as caught:
        run(registry, "reflectance", x, {"hdr": hdr})
    error = caught.value
    assert error.code == code and error.status_code == 400
    assert error.as_dict()["context"]["matched_criteria"] == matches
    assert all(match in error.as_dict()["detail"] for match in matches)


def test_requested_branch_cannot_override_hdr(registry):
    with pytest.raises(DataError, match="参数") as caught:
        run(registry, "reflectance", [[20,40]], {"hdr": {"reflectance scale factor": 100}, "branch": "passthrough"})
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
    assert caught.value.as_dict()["context"]["fields"][0]["field"] == "branch"


@pytest.mark.parametrize("guard", ["clip", "keep", "error"])
def test_negative_guards_and_counts(registry, guard):
    params = {"hdr": {"reflectance scale factor": 10}, "guard": guard}
    if guard == "error":
        with pytest.raises(DataError) as caught:
            run(registry, "reflectance", [[-10.,20.]], params)
        assert caught.value.code == "REFLECTANCE_GUARD_VIOLATION"
    else:
        result = run(registry, "reflectance", [[-10.,20.]], params)
        np.testing.assert_array_equal(result.spectra, [[0. if guard == "clip" else -1.,2.]])
        assert result.steps[0]["meta"]["negative_clipped"] == (1 if guard == "clip" else 0)


@pytest.mark.parametrize("guard", ["clip", "keep", "error"])
def test_zero_denominator_guards(registry, guard):
    params = {"hdr": {"white reference": "w", "dark reference": "d"},
              "white_reference": [1.,3.], "dark_reference": [1.,1.], "guard": guard}
    if guard == "error":
        with pytest.raises(DataError) as caught:
            run(registry, "reflectance", [[2.,2.]], params)
        assert caught.value.code == "REFLECTANCE_GUARD_VIOLATION"
    else:
        result = run(registry, "reflectance", [[2.,2.]], params)
        assert (np.isnan(result.spectra[0,0]) if guard == "clip" else np.isinf(result.spectra[0,0]))
        assert result.spectra[0,1] == .5
        assert result.steps[0]["meta"]["nan_bands"] == (1 if guard == "clip" else 0)


def test_nonfinite_denominator_and_input_nan_propagation(registry):
    params = {"hdr": {"white reference": "w", "dark reference": "d"},
              "white_reference": np.array([np.inf,2.,2.,2.,2.]), "dark_reference": np.zeros(5)}
    pipeline = {"steps": [{"op":"reflectance","version":1,"params":params},
                          {"op":"sg_smooth","version":1,"params":{"window":3,"polyorder":1}}]}
    axis = np.array([410.,420.,435.,450.,490.])
    result = registry.run([[1.,np.nan,1.,1.,1.]], pipeline, wavelengths=axis)
    assert result.steps[0]["meta"]["nan_bands"] == 2
    assert np.isnan(result.spectra[0,:3]).all()
    assert result.spectra.shape == (1,5)
    np.testing.assert_array_equal(result.wavelengths, axis)
    json.dumps(result.steps, allow_nan=False)


@pytest.mark.parametrize("change", [{"guard":"guess"}, {"white_reference":[[1,2]]}, {"free_text":"x"}])
def test_params_schema_rejects_bad_shape_unknown_keys_and_guard(registry, change):
    with pytest.raises(DataError) as caught:
        run(registry, "reflectance", [[1.,2.]], {"hdr":{"reflectance scale factor":10}, **change})
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
    assert caught.value.as_dict()["context"]["fields"][0]["message"]


def test_reference_branch_requires_resolved_band_aligned_inputs(registry):
    with pytest.raises(DataError) as caught:
        run(registry, "reflectance", [[10.,20.]], {"hdr":{"white reference":"w","dark reference":"d"}})
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
