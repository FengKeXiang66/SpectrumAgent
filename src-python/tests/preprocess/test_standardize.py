"""TASK-05 §5 B05/R8: independent formulas, fit-on-apply and zero scales."""
import json

import numpy as np
import pytest

from spectrumagent.data import DataError
from .conftest import run


@pytest.mark.parametrize("method", ["standard", "minmax", "area", "vector"])
def test_four_methods_formula_fit_metadata_and_determinism(registry, method):
    x = np.array([[1.,2.,4.],[3.,5.,8.],[6.,9.,15.]])
    before = x.copy()
    if method == "standard":
        expected = (x-x.mean(axis=0))/x.std(axis=0,ddof=0)
    elif method == "minmax":
        expected = (x-x.min(axis=0))/(x.max(axis=0)-x.min(axis=0))
    elif method == "area":
        areas = (x[:,0]/2+x[:,1]+x[:,2]/2)[:,None]
        expected = x/areas
    else:
        expected = x/np.sqrt((x*x).sum(axis=1))[:,None]
    first = run(registry,"standardize",x,{"method":method})
    second = run(registry,"standardize",x,{"method":method})
    np.testing.assert_allclose(first.spectra,expected,rtol=0,atol=1e-12)
    np.testing.assert_array_equal(first.spectra,second.spectra)
    np.testing.assert_array_equal(x,before)
    meta = first.steps[0]["meta"]
    assert set(meta) == {"method","fitted","n_spectra","zero_scale_count"}
    assert meta["method"] == method and meta["n_spectra"] == 3 and meta["zero_scale_count"] == 0
    if method == "standard":
        assert meta["fitted"] == [{"mean":float(x[:,i].mean()),"std":float(x[:,i].std(ddof=0))} for i in range(3)]
    elif method == "minmax":
        assert meta["fitted"] == [{"min":float(x[:,i].min()),"max":float(x[:,i].max())} for i in range(3)]
    else:
        assert meta["fitted"] == []
    json.dumps(first.steps,allow_nan=False)


@pytest.mark.parametrize("method", ["standard", "minmax", "area", "vector"])
@pytest.mark.parametrize("policy", ["zeros", "nan", "error"])
def test_zero_denominators_three_policies_and_error_context(registry, method, policy):
    x = np.array([[2.,1.,3.],[2.,4.,6.]]) if method in ("standard","minmax") else np.array([[0.,0.,0.],[1.,2.,3.]])
    if policy == "error":
        with pytest.raises(DataError) as caught:
            run(registry,"standardize",x,{"method":method,"zero_std":policy})
        assert caught.value.code == "NORMALIZATION_DEGENERATE" and caught.value.status_code == 400
        assert caught.value.as_dict()["context"] == {"zero_scale_count":1}
    else:
        result = run(registry,"standardize",x,{"method":method,"zero_std":policy})
        zero_values = result.spectra[:,0] if method in ("standard","minmax") else result.spectra[0]
        assert (np.all(zero_values == 0) if policy == "zeros" else np.isnan(zero_values).all())
        assert result.steps[0]["meta"]["zero_scale_count"] == 1


def test_fit_recomputed_per_input_no_calibration_in_recipe(registry):
    pipeline = {"steps":[{"op":"standardize","version":1,"params":{"method":"standard"}}]}
    a = registry.run([[1.,2.],[3.,6.]],pipeline)
    b = registry.run([[11.,12.],[13.,16.]],pipeline)
    assert a.steps[0]["meta"]["fitted"] != b.steps[0]["meta"]["fitted"]
    assert pipeline["steps"][0]["params"] == {"method":"standard"}


def test_signed_area_uses_band_index_not_wavelength_and_does_not_abs(registry):
    x = np.array([[1.,2.,4.],[-1.,0.,1.]])
    result = run(registry,"standardize",x,{"method":"area"},wavelengths=[400.,405.,800.])
    np.testing.assert_allclose(result.spectra[0],x[0]/4.5,rtol=0,atol=1e-12)
    assert np.all(result.spectra[1] == 0) and result.steps[0]["meta"]["zero_scale_count"] == 1


@pytest.mark.parametrize("method", ["standard","minmax","area","vector"])
def test_nan_not_filled_and_metadata_remains_json_safe(registry,method):
    result = run(registry,"standardize",[[1.,np.nan,3.],[2.,4.,6.]],{"method":method})
    assert np.isnan(result.spectra[0]).any()
    json.dumps(result.steps,allow_nan=False)


@pytest.mark.parametrize("params", [{"method":"unknown"},{"method":"vector","zero_std":"epsilon"},{"method":"standard","fitted":[1]}])
def test_unknown_params_rejected(registry,params):
    with pytest.raises(DataError) as caught:
        run(registry,"standardize",[[1.,2.]],params)
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
