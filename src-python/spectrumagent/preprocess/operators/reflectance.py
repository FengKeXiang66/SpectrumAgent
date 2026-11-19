"""B01/R6: hdr criteria choose a unique branch; no reference file I/O."""
import numpy as np

from spectrumagent.data.readers.header import CODES, key_name
from ..registry import PreprocessError, invalid


def reflectance(spectra, params):
    x = np.asarray(spectra, dtype=np.float64)
    hdr = {key_name(key): value for key, value in params["hdr"].items()}
    matches = []
    if hdr.get("whitereference") and hdr.get("darkreference"):
        matches.append("reference")
    if "scale_factor" in hdr:
        matches.append("scale")
    dtype = hdr.get("data_type")
    try:
        dtype = np.dtype(CODES.get(int(dtype), "?")) if str(dtype).isdigit() else np.dtype(dtype) if dtype is not None else None
    except (ValueError, TypeError):
        dtype = None
    if dtype is not None and dtype.kind == "f" and np.all(np.isfinite(x) & (x >= 0) & (x <= 1)):
        matches.append("passthrough")
    if len(matches) != 1:
        code = "AMBIGUOUS_REFLECTANCE_INPUT" if matches else "UNKNOWN_REFLECTANCE_INPUT"
        raise PreprocessError(code, "反射率判据命中：" + (", ".join(matches) if matches else "无"), matched_criteria=matches)
    branch = matches[0]
    if params["branch"] is not None and params["branch"] != branch:
        raise invalid("branch", "请求分支与 hdr 判据不一致")
    bad_input = ~np.isfinite(x)
    if branch == "reference":
        references = []
        for name in ("white_reference", "dark_reference"):
            value = params[name]
            if value is None or len(value) != x.shape[1]:
                raise invalid(name, "reference 分支须提供与 bands 等长的已解析参考谱")
            references.append(np.asarray(value, dtype=np.float64))
        white, dark = references
        numerator, denominator = x-dark, white-dark
        bad_input = bad_input | ~np.isfinite(white) | ~np.isfinite(dark)
    elif branch == "scale":
        try:
            denominator = float(hdr["scale_factor"])
        except (ValueError, TypeError) as error:
            raise invalid("hdr.reflectance scale factor", "scale factor 必须是数值") from error
        numerator = x
    else:
        numerator, denominator = x, 1.
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        output = numerator / denominator
    negative = output < 0
    bad_denominator = (np.asarray(denominator) == 0) | ~np.isfinite(denominator)
    guard = params["guard"]
    if guard == "error" and (np.any(negative) or np.any(bad_denominator)):
        raise PreprocessError("REFLECTANCE_GUARD_VIOLATION", "反射率包含负值或零/非有限分母", branch=branch, guard=guard)
    clipped = 0
    if guard == "clip":
        clipped = int(np.count_nonzero(negative & ~(bad_input | bad_denominator)))
        output = np.where(negative, 0., output)
        output = np.where(bad_input | bad_denominator, np.nan, output)
    return output, {"branch": branch, "matched_criteria": matches, "guard": guard,
                    "negative_clipped": clipped, "nan_bands": int(np.count_nonzero(np.isnan(output)))}
