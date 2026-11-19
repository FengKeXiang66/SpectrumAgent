"""B02/B03: same band axis; R7 strict order bound and fixed per-index delta."""
import numpy as np
from scipy.signal import savgol_filter

from ..registry import invalid


def _filter(spectra, params, order):
    if params["mode"] == "interp" and params["window"] > spectra.shape[1]:
        raise invalid("window", "interp 窗口不得超过输入 bands")
    options = {"window_length": params["window"], "polyorder": params["polyorder"],
               "deriv": order, "delta": 1., "axis": -1}
    if params["mode"] != "interp" or np.isfinite(spectra).all():
        return savgol_filter(spectra, **options, mode=params["mode"])
    # SciPy's interp edge least-squares rejects nonfinite targets. Preserve the
    # same convolution internally; only fit finite edge windows. An unavailable
    # edge fit propagates NaN to that edge, never fills/replaces source values.
    output = savgol_filter(spectra, **options, mode="constant")
    half = params["window"] // 2
    if half:
        for window, edge in ((slice(0, params["window"]), slice(0, half)),
                             (slice(-params["window"], None), slice(-half, None))):
            values = spectra[:, window]
            valid = np.isfinite(values).all(axis=1)
            output[:, edge] = np.nan
            if np.any(valid):
                fitted = savgol_filter(values[valid], **options, mode="interp")
                output[valid, edge] = fitted[:, :half] if window.start == 0 else fitted[:, -half:]
    return output


def smooth(spectra, params):
    return _filter(spectra, params, 0)


def derivative(spectra, params):
    return _filter(spectra, params, params["order"]), {
        "order": params["order"], "window": params["window"], "polyorder": params["polyorder"],
        "mode": params["mode"], "unit": "band_index"}
