import json
from pathlib import Path

import numpy as np

from ..errors import DataError
from ..model import MemmapAccess, SpectrumDataSet
from .header import classic, normalize, read_text, resolve_data, validate_size


def json_object(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise DataError("HEADER_INVALID", "JSON头包含重复键", field=key)
            result[key] = value
        return result
    def nonfinite(value):
        raise DataError("HEADER_INVALID", "JSON头不能包含NaN或Infinity")
    try:
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, TypeError) as exc:
        raise DataError("HEADER_INVALID", "JSON头损坏") from exc
    if not isinstance(result, dict):
        raise DataError("HEADER_INVALID", "JSON头必须为对象")
    return result


def mapped_dataset(path, header, data_path=None, *, raw=False, reader="binary"):
    data = resolve_data(path, header, data_path)
    validate_size(data, header)
    lines, samples, bands = header.shape
    def mapping():
        validate_size(data, header)
        physical_shape = (lines, samples, bands) if header.interleave == "bip" else (lines, bands, samples) if header.interleave == "bil" else (bands, lines, samples)
        physical = np.memmap(data, dtype=header.dtype, mode="r", offset=header.offset, shape=physical_shape)
        return physical if header.interleave == "bip" else physical.transpose(0, 2, 1) if header.interleave == "bil" else physical.transpose(1, 2, 0)
    class Access(MemmapAccess):
        def asarray(self):
            validate_size(data, header)
            return super().asarray()
    metadata = dict(header.metadata, scale_factor=header.scale, scale_applied=not raw, value_mode="raw_dn" if raw else "reflectance", value_description=f"DN原值，未除scale factor={header.scale:g}" if raw else f"float64，DN / {header.scale:g}", byte_order=0 if header.dtype.byteorder in ("<", "=", "|") else 1, header_offset=header.offset, reader=reader)
    return SpectrumDataSet(name=path.stem, shape=header.shape, dtype=header.dtype.name, interleave=header.interleave, wavelengths=header.wavelengths, fwhm=header.fwhm, data_path=str(data), header_path=str(path), metadata=metadata).bind(Access(mapping), raw=raw, scale_factor=header.scale)


class BinaryReader:
    def open(self, data_path, header_path, *, raw=False):
        path = Path(header_path).resolve()
        text = read_text(path)
        fields = json_object(text) if path.suffix.lower() == ".json" or text.lstrip().startswith("{") else classic(text, magic=False)
        return mapped_dataset(path, normalize(fields), data_path, raw=raw)
