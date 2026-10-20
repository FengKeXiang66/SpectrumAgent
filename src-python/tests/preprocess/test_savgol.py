"""TASK-05 §5 B02/B03; R7 strict inequality, no wavelength-unit derivative."""
import numpy as np
import pytest
from scipy.signal import savgol_filter

from spectrumagent.data import DataError
from .conftest import run


@pytest.mark.parametrize("name", ["sg_smooth", "sg_derivative"])
@pytest.mark.parametrize("window,polyorder,field", [(4,2,"window"),(5,5,"polyorder"),(5,6,"polyorder")])
def test_even_window_and_polyorder_ge_window_structured_before_scipy(registry, monkeypatch, name, window, polyorder, field):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid parameters reached scipy")
    monkeypatch.setattr("spectrumagent.preprocess.operators.savgol.savgol_filter", forbidden)
    params = {"window":window,"polyorder":polyorder, **({"order":1} if name == "sg_derivative" else {})}
    with pytest.raises(DataError) as caught:
        run(registry, name, np.ones((2,11)), params)
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
    assert any(item["field"].endswith(field) for item in caught.value.as_dict()["context"]["fields"])


@pytest.mark.parametrize("mode", ["interp","mirror","constant","nearest","wrap"])
def test_smoothing_modes_and_configurable_window_order(registry, mode):
    x = np.array([[1.,2.,3.,2.,5.,8.,7.,3.,2.]])
    for window, polyorder in ((3,1),(5,2)):
        result = run(registry, "sg_smooth", x, {"window":window,"polyorder":polyorder,"mode":mode})
        np.testing.assert_array_equal(result.spectra, savgol_filter(x,window,polyorder,axis=-1,mode=mode))
        assert result.steps[0]["params"]["mode"] == mode


@pytest.mark.parametrize("order", [1,2])
def test_derivative_polynomial_per_band_index_and_unchanged_nonuniform_axis(registry, order):
    t = np.arange(17,dtype=np.float64)
    x = (3*t*t+2*t+7)[None,:]
    axis = 400 + t*t
    params = {"window":5,"polyorder":2,"order":order}
    result = run(registry,"sg_derivative",x,params,wavelengths=axis)
    expected = (6*t+2)[None,:] if order == 1 else np.full_like(x,6.)
    np.testing.assert_allclose(result.spectra,expected,rtol=0,atol=1e-10)
    np.testing.assert_array_equal(result.wavelengths,axis)
    assert result.steps[0]["meta"] == {**params,"mode":"interp","unit":"band_index"}
    assert "delta" not in registry.entries["sg_derivative"][1].params_schema["properties"]


@pytest.mark.parametrize("change", [{"delta":2.},{"order":3},{"order":True},{"window":3.5},{"polyorder":True},{"mode":"unknown"}])
def test_no_delta_or_bad_types_orders_modes(registry, change):
    with pytest.raises(DataError) as caught:
        run(registry,"sg_derivative",np.ones((1,9)),{"window":5,"polyorder":2,"order":1,**change})
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"


def test_window_longer_than_axis_is_structured(registry):
    with pytest.raises(DataError) as caught:
        run(registry,"sg_smooth",[[1.,2.,3.]],{"window":5,"polyorder":2})
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"


@pytest.mark.parametrize("name,order", [("sg_smooth",0),("sg_derivative",1),("sg_derivative",2)])
@pytest.mark.parametrize("mode", ["interp","mirror","constant","nearest","wrap"])
def test_nan_windows_propagate_without_imputation_and_finite_windows_unchanged(registry,name,order,mode):
    clean = np.arange(15,dtype=np.float64)[None,:]**2
    x = clean.copy()
    x[0,1] = np.nan
    params = {"window":5,"polyorder":2,"mode":mode,**({"order":order} if order else {})}
    result = run(registry,name,x,params)
    expected = savgol_filter(clean,5,2,deriv=order,axis=-1,mode=mode)
    assert np.isnan(result.spectra[0,1])
    # Far from the missing value and the opposite boundary: identical SG values.
    np.testing.assert_allclose(result.spectra[:,5:10],expected[:,5:10],rtol=0,atol=1e-12)
    assert result.spectra.shape == x.shape and np.isnan(x[0,1])


def test_interp_nan_last_edge_and_all_nan_rows_remain_nan(registry):
    x = np.array([[1.,2.,3.,4.,5.,6.,np.nan],[np.nan]*7])
    result = run(registry,"sg_smooth",x,{"window":3,"polyorder":1})
    assert np.isnan(result.spectra[0,-2:]).all() and np.isnan(result.spectra[1]).all()
    np.testing.assert_allclose(result.spectra[0,:4],[1.,2.,3.,4.],rtol=0,atol=1e-12)
