import numpy as np
import pytest

from .conftest import run


@pytest.mark.parametrize("method", ["convex_hull", "linear"])
def test_b09_fixed_endpoints_same_axis_and_reproducible(registry, method):
    x = np.array([[1., 2., .4, 2., 1.]])
    axis = np.arange(5.)+400
    result = run(registry, "continuum", x, {"method": method}, wavelengths=axis)
    expected = [[1., 1., .2, 1., 1.]] if method == "convex_hull" else x
    np.testing.assert_allclose(result.spectra, expected, atol=1e-12)
    np.testing.assert_array_equal(result.wavelengths, axis)
    assert result.steps[0]["meta"]["hull_vertex_counts"] == [4 if method == "convex_hull" else 2]


@pytest.mark.parametrize("method", ["convex_hull", "linear"])
def test_continuum_zero_denominator_nan_and_count(registry, method):
    result = run(registry, "continuum", [[0., 0., 0.]], {"method": method})
    assert np.isnan(result.spectra).all()
    assert result.steps[0]["meta"]["zero_continuum_bands"] == 3
