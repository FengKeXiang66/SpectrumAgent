"""B05/R8: fit on the supplied pixel spectra, no stored calibration or run IO."""
import numpy as np

from ..registry import PreprocessError


def standardize(spectra, params):
    x = np.asarray(spectra, dtype=np.float64)
    method = params["method"]
    if method == "standard":
        offset = x.mean(axis=0)
        scale = x.std(axis=0, ddof=0)
        numerator = x-offset
        fitted = [{"mean": float(mean), "std": float(std)} for mean, std in zip(offset, scale)]
    elif method == "minmax":
        low, high = x.min(axis=0), x.max(axis=0)
        scale = high-low
        numerator = x-low
        fitted = [{"min": float(lo), "max": float(hi)} for lo, hi in zip(low, high)]
    elif method == "area":
        scale = np.trapezoid(x, dx=1.0, axis=1)[:, None]
        numerator, fitted = x, []
    else:  # Schema constrains the remaining method to vector.
        scale = np.linalg.norm(x, axis=1)[:, None]
        numerator, fitted = x, []
    zero = scale == 0
    count = int(np.count_nonzero(zero))
    if count and params["zero_std"] == "error":
        raise PreprocessError("NORMALIZATION_DEGENERATE", "归一化分母为零", zero_scale_count=count)
    with np.errstate(divide="ignore", invalid="ignore"):
        output = numerator/scale
    if count:
        output = np.where(zero, 0. if params["zero_std"] == "zeros" else np.nan, output)
    return output, {"method": method, "fitted": fitted, "n_spectra": len(x), "zero_scale_count": count}
