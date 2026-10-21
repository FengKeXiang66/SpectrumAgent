"""B08 deterministic FastICA; the run feeds a single temporary memmap."""
import numpy as np
from sklearn.decomposition import FastICA

from ..registry import PreprocessError
from .pca import component_count, orient, transform, variance_meta


def fit_ica(finite, params, *, nan_count=0):
    k = component_count(params, finite.shape[1])
    if len(finite) < max(2, k):
        raise PreprocessError("DECOMPOSITION_DEGENERATE", "ICA 有限谱数不足", n_spectra=len(finite))
    try:
        model = FastICA(n_components=k, random_state=params["random_state"])
        model.fit(finite)
    except (ValueError, np.linalg.LinAlgError) as error:
        raise PreprocessError("DECOMPOSITION_DEGENERATE", "FastICA 无法拟合输入", reason=str(error)) from error
    loadings, signs = orient(model.components_.T)
    # No full score matrix: accumulate reconstruction-energy diagnostics by row.
    total = np.zeros(k)
    squares = np.zeros(k)
    for row in finite:
        score = (row-model.mean_) @ loadings
        total += score
        squares += score*score
    variances = (squares-total*total/len(finite))/(len(finite)-1)
    energies = variances*np.sum(model.mixing_**2, axis=0)
    meta = {"method": "ica", "axis": None, "loadings": loadings.tolist(),
            "mean": model.mean_.tolist(), "random_state": params["random_state"],
            "n_spectra": len(finite), "nan_spectra": nan_count,
            "variance_definition": "实现层口径：var(score,ddof=1)*||mixing_column||²；非正交分量重构能量占比，非 PCA 方差分解",
            "estimator": "sklearn.decomposition.FastICA library defaults; random_state from params",
            **variance_meta(energies)}
    return model.mean_, loadings, meta


def ica(spectra, params):
    x = np.asarray(spectra, dtype=np.float64)
    component_count(params, x.shape[1])
    valid = np.isfinite(x).all(axis=1)
    mean, loadings, meta = fit_ica(x[valid], params, nan_count=int((~valid).sum()))
    return transform(x, mean, loadings), meta
