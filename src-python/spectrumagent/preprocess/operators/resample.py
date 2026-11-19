"""B06/R8/R9: linear/spline, no extrapolation, median-interval FWHM proxy."""
import numpy as np
from scipy.interpolate import CubicSpline

from ..registry import invalid


def resample(spectra, params):
    source = np.asarray(params["source"], dtype=np.float64)
    target = np.asarray(params["target"], dtype=np.float64)
    if len(source) != spectra.shape[1]:
        raise invalid("source", "source 长度必须等于输入 bands")
    outside = (target < source[0]) | (target > source[-1])
    if params["method"] == "linear":
        output = np.stack([np.interp(target, source, row, left=np.nan, right=np.nan) for row in spectra])
    else:
        # A NaN source row cannot be fitted. Preserve it explicitly, without filling.
        valid = np.isfinite(spectra).all(axis=1)
        output = np.full((len(spectra), len(target)), np.nan, np.float64)
        if np.any(valid):
            output[valid] = CubicSpline(source, spectra[valid], axis=1, extrapolate=False)(target)
    output[:, outside] = np.nan
    before = float(np.median(np.diff(source)))
    after = float(np.median(np.diff(target)))
    return output, {"axis": target, "out_of_range_bands": int(outside.sum()),
                    "fwhm_before": before, "fwhm_after": after,
                    "fwhm_warning": bool(abs(after-before)/before > .05),
                    "fwhm_note": "间隔代理值非实测分辨率"}
