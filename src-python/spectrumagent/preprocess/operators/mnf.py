"""B08 MNF: TASK-05 §2.6 R12 adjacent-band noise reconstruction verbatim."""
import numpy as np

from ..registry import PreprocessError
from .pca import component_count, covariance, orient, transform, variance_meta


def noise_covariance(difference):
    bands = len(difference)+1
    if bands < 2:
        raise PreprocessError("DECOMPOSITION_DEGENERATE", "MNF 至少需要两个波段")
    diagonal = np.diag(difference)
    variances = np.empty(bands)
    variances[0], variances[-1] = diagonal[0]/2, diagonal[-1]/2
    variances[1:-1] = (diagonal[:-1]+diagonal[1:])/2
    noise = np.diag(variances)
    off = (variances[:-1]+variances[1:]-diagonal)/2
    noise[np.arange(bands-1), np.arange(1, bands)] = off
    noise[np.arange(1, bands), np.arange(bands-1)] = off
    return noise


def fit_mnf(factory, params):
    mean, signal, difference, count, nan_count = covariance(factory)
    k = component_count(params, len(mean))
    noise = noise_covariance(difference)
    values, vectors = np.linalg.eigh(noise)
    if np.any(values < 0):
        raise PreprocessError("DECOMPOSITION_DEGENERATE", "R12 噪声协方差非半正定，无法实数白化",
                              minimum_noise_eigenvalue=float(values.min()))
    root = (vectors*np.sqrt(values)) @ vectors.T
    whitening = np.linalg.pinv(root, hermitian=True)
    values, vectors = np.linalg.eigh(whitening @ signal @ whitening)
    indices = np.argsort(values)[::-1]
    values = values[indices]
    loadings, _ = orient(whitening @ vectors[:, indices[:k]])
    meta = {"method": "mnf", "axis": None, "loadings": loadings.tolist(), "mean": mean.tolist(),
            "random_state": params["random_state"], "n_spectra": count, "nan_spectra": nan_count,
            "noise_estimator": "TASK-05 §2.6 R12: adjacent-band delta.T@delta/(n-1), tridiagonal BxB reconstruction; eigh + pinv sqrt",
            "noise_covariance": noise.tolist(), **variance_meta(values)}
    return mean, loadings, meta


def mnf(spectra, params):
    x = np.asarray(spectra, dtype=np.float64)
    component_count(params, x.shape[1])
    mean, loadings, meta = fit_mnf(lambda: iter((x,)), params)
    return transform(x, mean, loadings), meta
