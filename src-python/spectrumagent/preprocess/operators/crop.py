"""B06/R8/R9: explicit source axis, closed range, immutable pixel alignment."""
import numpy as np

from ..registry import invalid


def crop(spectra, params):
    source = np.asarray(params["source"], dtype=np.float64)
    if len(source) != spectra.shape[1]:
        raise invalid("source", "source 长度必须等于输入 bands")
    lo, hi = params["range"]
    selected = (source >= lo) & (source <= hi)
    if not np.any(selected):
        raise invalid("range", "闭区间内没有命中波段")
    return spectra[:, selected].copy(), {"axis": source[selected]}
