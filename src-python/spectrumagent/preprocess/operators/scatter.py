"""B04/R8: deterministic population SNV and explicit-reference least squares."""
import hashlib

import numpy as np

from ..registry import PreprocessError, invalid


def fingerprint(array):
    return hashlib.sha256(np.ascontiguousarray(array, dtype=np.float64).tobytes(order="C")).hexdigest()


def snv(spectra, params):
    x = np.asarray(spectra, dtype=np.float64)
    mean = x.mean(axis=1, keepdims=True)
    std = x.std(axis=1, keepdims=True, ddof=0)
    zero = std[:, 0] == 0
    if params["zero_std"] == "error" and np.any(zero):
        raise PreprocessError("SCATTER_MODEL_DEGENERATE", "SNV 输入包含零方差谱", zero_std_count=int(zero.sum()))
    with np.errstate(divide="ignore", invalid="ignore"):
        output = (x-mean)/std
    if params["zero_std"] == "zeros":
        output[zero] = 0.
    return output, {"method": "snv", "reference_sha256": None, "reference_len": None,
                    "std_ddof": 0, "zero_std_count": int(zero.sum())}


def _correct(spectra, params, order, method):
    x = np.asarray(spectra, dtype=np.float64)
    reference = np.asarray(params["reference"], dtype=np.float64)
    if len(reference) != x.shape[1]:
        raise invalid("reference", "参考谱长度必须等于 bands")
    t = np.linspace(0., 1., x.shape[1])
    design = np.column_stack([reference, np.ones(len(t)), *[t**k for k in range(1, order+1)]])
    _, _, rank, _ = np.linalg.lstsq(design, np.zeros(len(t)), rcond=None)
    if rank < design.shape[1]:
        raise PreprocessError("SCATTER_MODEL_DEGENERATE", "散射校正设计矩阵秩不足",
                              design_rank=int(rank), expected_columns=design.shape[1])
    nan_rows = np.isnan(x).any(axis=1)
    output = np.full(x.shape, np.nan, np.float64)
    coefficients = np.full((len(x), design.shape[1]), np.nan, np.float64)
    zero_scale_count = 0
    for i in np.flatnonzero(~nan_rows):
        fitted, _, _, _ = np.linalg.lstsq(design, x[i], rcond=None)
        coefficients[i] = fitted
        scale = fitted[0]
        if scale == 0. or np.isnan(scale):
            zero_scale_count += 1
            continue
        baseline = design[:, 1:] @ fitted[1:]
        output[i] = (x[i]-baseline)/scale
    meta = {"method": method, "reference_sha256": fingerprint(reference), "reference_len": len(reference),
            "std_ddof": None, "zero_std_count": 0,
            "coefficients_shape": list(coefficients.shape), "coefficients_sha256": fingerprint(coefficients),
            "zero_scale_count": zero_scale_count, "nan_spectra": int(nan_rows.sum())}
    if method == "emsc":
        meta["emsc_order"] = order
    return output, meta


def msc(spectra, params):
    return _correct(spectra, params, 0, "msc")


def emsc(spectra, params):
    return _correct(spectra, params, params["polynomial_order"], "emsc")
