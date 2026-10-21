"""TASK-05 §5 B06/R8: explicit axes, closed crop, interpolation and proxy."""
import json

import numpy as np
import pytest

from spectrumagent.data import DataError
from .conftest import run


def test_crop_closed_range_preserves_endpoints_single_hit_and_explicit_source(registry):
    source = [400.,500.,600.,700.]
    x = np.array([[1.,2.,3.,4.],[5.,6.,7.,8.]])
    result = run(registry,"crop",x,{"source":source,"range":[500.,700.]},wavelengths=[1.,2.,3.,4.])
    np.testing.assert_array_equal(result.spectra,x[:,1:])
    np.testing.assert_array_equal(result.wavelengths,[500.,600.,700.])
    single = run(registry,"crop",x,{"source":source,"range":(499.,501.)})
    assert single.spectra.shape == (2,1) and single.wavelengths.tolist() == [500.]


def test_crop_empty_and_source_mismatch_structured(registry):
    for params in ({"source":[1.,2.,3.],"range":(4.,5.)},{"source":[1.,2.],"range":(1.,2.)}):
        with pytest.raises(DataError) as caught:
            run(registry,"crop",[[1.,2.,3.]],params)
        assert caught.value.code == "INVALID_OPERATOR_PARAMS"


@pytest.mark.parametrize("name,params", [
    ("crop",{"source":[1.,1.,3.],"range":(1.,3.)}),
    ("crop",{"source":[1.,np.nan,3.],"range":(1.,3.)}),
    ("crop",{"source":[1.,2.,3.],"range":(3.,1.)}),
    ("crop",{"source":[1.,2.,3.],"range":(2.,2.)}),
    ("crop",{"source":[1.,2.,3.],"range":(1.,2.,3.)}),
    ("resample",{"source":[1.,3.,2.],"target":[1.,2.],"method":"linear"}),
    ("resample",{"source":[1.,2.,3.],"target":[1.,1.],"method":"linear"}),
    ("resample",{"source":[1.,2.,3.],"target":[1.,np.inf],"method":"linear"}),
])
def test_axis_and_range_fail_at_schema_level(registry,name,params):
    with pytest.raises(DataError) as caught:
        run(registry,name,[[1.,2.,3.]],params)
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
    assert caught.value.as_dict()["context"]["fields"]


@pytest.mark.parametrize("method", ["linear","spline"])
def test_interpolation_formula_and_no_clamp_or_extrapolation(registry,method):
    source = np.array([0.,1.,2.,4.,5.])
    target = np.array([-1.,0.,.5,1.5,3.,5.,6.])
    x = 2*source+3 if method == "linear" else source**3+2*source+3
    expected = 2*target+3 if method == "linear" else target**3+2*target+3
    result = run(registry,"resample",np.stack([x,x+2]),{"source":source,"target":target,"method":method})
    np.testing.assert_allclose(result.spectra[0,1:-1],expected[1:-1],rtol=0,atol=1e-12)
    np.testing.assert_allclose(result.spectra[1,1:-1],expected[1:-1]+2,rtol=0,atol=1e-12)
    assert np.isnan(result.spectra[:,[0,-1]]).all()
    assert result.steps[0]["meta"]["out_of_range_bands"] == 2
    np.testing.assert_array_equal(result.wavelengths,target)
    json.dumps(result.steps,allow_nan=False)


def test_fwhm_is_median_not_mean_and_proxy_marked(registry):
    result = run(registry,"resample",[[0.,1.,2.,12.]],{"source":[0.,1.,2.,12.],"target":[0.,2.,4.,6.],"method":"linear"})
    meta = result.steps[0]["meta"]
    assert meta["fwhm_before"] == 1 and meta["fwhm_after"] == 2 and meta["fwhm_warning"] is True
    assert meta["fwhm_note"] == "间隔代理值非实测分辨率"


@pytest.mark.parametrize("spacing,warning", [(20.,False),(21.,False),(22.,True),(19.,False),(18.,True)])
def test_fwhm_strictly_greater_than_five_percent(registry,spacing,warning):
    result = run(registry,"resample",[[1.,2.,3.]],{"source":[0.,20.,40.],"target":[0.,spacing,2*spacing],"method":"linear"})
    assert result.steps[0]["meta"]["fwhm_warning"] is warning


@pytest.mark.parametrize("name,params", [("crop",{"range":(1.,3.)}),("resample",{"target":[1.,2.],"method":"linear"})])
def test_runtime_wavelengths_do_not_supply_missing_source(registry,name,params):
    with pytest.raises(DataError) as caught:
        run(registry,name,[[1.,2.,3.]],params,wavelengths=[1.,2.,3.])
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"


def test_spline_nan_row_propagates_without_filling(registry):
    result = run(registry,"resample",[[1.,np.nan,3.],[2.,3.,4.]],{"source":[1.,2.,3.],"target":[1.,1.5,2.,3.],"method":"spline"})
    assert np.isnan(result.spectra[0]).all() and np.isfinite(result.spectra[1]).all()
