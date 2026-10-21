"""B08: two-pass covariance PCA, shared by pure and bounded run execution."""
import numpy as np

from ..registry import PreprocessError, invalid


def component_count(params, bands):
    count = params["n_components"]
    if count > bands:
        raise invalid("n_components", "n_components 不得超过输入 bands")
    return count


def covariance(factory):
    """Factory yields stable logical lines, irrespective of disk block size."""
    total = None
    count = nan_count = 0
    for block in factory():
        valid = np.isfinite(block).all(axis=1)
        finite = block[valid]
        nan_count += int((~valid).sum())
        if total is None:
            total = np.zeros(block.shape[1], dtype=np.float64)
        total += finite.sum(axis=0)
        count += len(finite)
    if count < 2:
        raise PreprocessError("DECOMPOSITION_DEGENERATE", "降维拟合至少需要两条有限谱", n_spectra=count)
    mean = total / count
    signal = np.zeros((len(mean), len(mean)), dtype=np.float64)
    difference = np.zeros((len(mean)-1, len(mean)-1), dtype=np.float64)
    for block in factory():
        finite = block[np.isfinite(block).all(axis=1)]
        centered = finite-mean
        signal += centered.T @ centered
        delta = np.diff(finite, axis=1)
        difference += delta.T @ delta
    return mean, signal/(count-1), difference/(count-1), count, nan_count


def orient(loadings):
    signs = np.where(loadings[np.argmax(np.abs(loadings), axis=0), np.arange(loadings.shape[1])] < 0, -1., 1.)
    return loadings*signs, signs


def variance_meta(values):
    total = float(np.sum(values))
    ratios = values/total if total != 0 else np.zeros_like(values)
    return {"explained_variance": values.tolist(), "explained_variance_ratio": ratios.tolist(),
            "cumulative_explained_variance": np.cumsum(ratios).tolist()}


def fit_pca(factory, params):
    mean, signal, _, count, nan_count = covariance(factory)
    k = component_count(params, len(mean))
    values, vectors = np.linalg.eigh(signal)
    indices = np.argsort(values)[::-1]
    values = np.maximum(values[indices], 0.)
    loadings, _ = orient(vectors[:, indices[:k]])
    meta = {"method": "pca", "axis": None, "loadings": loadings.tolist(),
            "mean": mean.tolist(), "random_state": params["random_state"],
            "n_spectra": count, "nan_spectra": nan_count,
            "estimator": "TASK-05 §2.6 R12: two-pass centered covariance, ddof=1, numpy.linalg.eigh",
            **variance_meta(values)}
    return mean, loadings, meta


def transform(spectra, mean, loadings):
    x = np.asarray(spectra, dtype=np.float64)
    valid = np.isfinite(x).all(axis=1)
    output = np.full((len(x), loadings.shape[1]), np.nan)
    output[valid] = (x[valid]-mean) @ loadings
    return output


def pca(spectra, params):
    x = np.asarray(spectra, dtype=np.float64)
    component_count(params, x.shape[1])
    mean, loadings, meta = fit_pca(lambda: iter((x,)), params)
    return transform(x, mean, loadings), meta
