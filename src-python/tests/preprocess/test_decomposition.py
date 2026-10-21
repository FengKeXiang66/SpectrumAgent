import numpy as np
import pytest

from spectrumagent.data import DataError
from spectrumagent.preprocess.operators.mnf import noise_covariance
from spectrumagent.preprocess.schema import MscParams
from .conftest import run


@pytest.fixture
def pixels():
    return np.random.default_rng(121).uniform(.1, .9, (90, 8))


@pytest.mark.parametrize("op", ["pca", "mnf", "ica"])
def test_b08_scores_axis_loadings_sign_variance_and_repeat(registry, pixels, op):
    first = run(registry, op, pixels, {"n_components": 3}, wavelengths=np.arange(8))
    second = run(registry, op, pixels, {"n_components": 3})
    assert first.spectra.shape == (90, 3) and first.wavelengths is None
    np.testing.assert_allclose(first.spectra, second.spectra, rtol=0, atol=1e-12)
    meta = first.steps[0]["meta"]
    assert meta["axis_len"] is meta["axis_sha256"] is None and "axis" not in meta
    assert meta["random_state"] == 0 and meta["method"] == op
    loadings = np.asarray(meta["loadings"])
    assert np.all(loadings[np.argmax(abs(loadings), axis=0), np.arange(3)] >= 0)
    np.testing.assert_allclose(first.spectra, (pixels-meta["mean"]) @ loadings, atol=1e-12)
    assert "explained_variance" in meta and "cumulative_explained_variance" in meta


@pytest.mark.parametrize("op", ["pca", "mnf", "ica"])
def test_b08_nan_excluded_and_transformed_to_full_nan(registry, pixels, op):
    pixels[1, 0] = np.nan
    result = run(registry, op, pixels, {"n_components": 2})
    assert np.isnan(result.spectra[1]).all() and np.isfinite(result.spectra[np.arange(90) != 1]).all()
    assert result.steps[0]["meta"]["nan_spectra"] == 1


@pytest.mark.parametrize("op", ["pca", "mnf", "ica"])
@pytest.mark.parametrize("params", [{}, {"n_components": 0}, {"n_components": 9}])
def test_b08_component_bounds_structured(registry, pixels, op, params):
    with pytest.raises(DataError) as caught:
        run(registry, op, pixels, params)
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"


def test_ica_random_state_is_param_and_reserved_run_argument_is_unused(registry, pixels):
    first = run(registry, "ica", pixels, {"n_components": 3, "random_state": 2}, random_state=99)
    second = run(registry, "ica", pixels, {"n_components": 3, "random_state": 2})
    np.testing.assert_array_equal(first.spectra, second.spectra)
    assert first.steps[0]["params"]["random_state"] == 2


def test_mnf_r12_noise_reconstruction_and_singular_pinv(registry):
    difference = np.array([[2., .1], [.1, 4.]])
    expected = np.array([[1., 1., 0.], [1., 3., .5], [0., .5, 2.]])
    np.testing.assert_array_equal(noise_covariance(difference), expected)
    x = np.tile(np.arange(6.)[:, None], (1, 4))
    result = run(registry, "mnf", x, {"n_components": 2})
    assert np.isfinite(result.spectra).all()
    assert "pinv" in result.steps[0]["meta"]["noise_estimator"]


def test_mnf_independent_full_r12_formula_eigenvalues_and_scores(registry, pixels):
    # Independent oracle: no production covariance/noise/transform helper calls.
    n, bands = pixels.shape
    delta = pixels[:, 1:]-pixels[:, :-1]
    difference = delta.T @ delta/(n-1)
    noise = np.zeros((bands, bands))
    for i in range(bands):
        noise[i, i] = (difference[0, 0]/2 if i == 0 else difference[-1, -1]/2 if i == bands-1
                       else (difference[i-1, i-1]+difference[i, i])/2)
    for i in range(bands-1):
        noise[i, i+1] = noise[i+1, i] = (noise[i, i]+noise[i+1, i+1]-difference[i, i])/2
    values, vectors = np.linalg.eigh(noise)
    whitening = np.linalg.pinv((vectors*np.sqrt(values)) @ vectors.T, hermitian=True)
    centered = pixels-pixels.mean(axis=0)
    signal = centered.T @ centered/(n-1)
    values, vectors = np.linalg.eigh(whitening @ signal @ whitening)
    indices = np.argsort(values)[::-1]
    loadings = whitening @ vectors[:, indices[:3]]
    for column in range(3):
        if loadings[np.argmax(abs(loadings[:, column])), column] < 0:
            loadings[:, column] *= -1
    actual = run(registry, "mnf", pixels, {"n_components": 3})
    np.testing.assert_allclose(actual.steps[0]["meta"]["noise_covariance"], noise, atol=1e-12)
    np.testing.assert_allclose(actual.steps[0]["meta"]["explained_variance"], values[indices], atol=1e-12)
    np.testing.assert_allclose(actual.spectra, centered @ loadings, rtol=0, atol=1e-12)


@pytest.mark.parametrize("op,params", [
    ("crop", {"source": [1.], "range": [0., 2.]}),
    ("resample", {"source": [1.], "target": [1., 2.], "method": "spline"}),
    ("resample", {"source": [1., 2.], "target": [1.], "method": "linear"})])
def test_r10_axis_minimum_schema_guard_and_old_reference_unchanged(registry, op, params):
    with pytest.raises(DataError) as caught:
        run(registry, op, [[1.]], params)
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
    assert MscParams.model_validate({"reference": [1.]}).reference == [1.]
