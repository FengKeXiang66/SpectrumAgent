from pathlib import Path

import structlog

from ..errors import DataError
from .binary import json_object, mapped_dataset
from .envi import EnviReader
from .header import classic, key_name, normalize, read_text

log = structlog.get_logger("datasets.fallback")


class FallbackEnviReader:
    def open(self, header_path, data_path=None, *, raw=False):
        path = Path(header_path).resolve()
        text = read_text(path)
        if text.lstrip().startswith("{"):
            fields = json_object(text)
            wrapped = [key for key in fields if key_name(key) == "header"]
            if len(wrapped) > 1:
                raise DataError("HEADER_INVALID", "重复header包裹对象")
            if wrapped:
                header_key = wrapped[0]
                inner = fields.pop(header_key)
                if not isinstance(inner, dict):
                    raise DataError("HEADER_INVALID", "ENVI5 header必须为对象")
                # Other top-level keys are retained; duplicate normalized keys fail
                # rather than silently overwriting a conflicting inner declaration.
                for key, value in inner.items():
                    if key in fields:
                        raise DataError("HEADER_INVALID", "内外头字段冲突", field=key)
                    fields[key] = value
        else:
            fields = classic(text)
        return mapped_dataset(path, normalize(fields), data_path, raw=raw, reader="fallback_envi")


def open_envi(header_path, data_path=None, *, raw=False):
    """Standard spectral -> permissive header adapter -> explicit structured error."""
    try:
        return EnviReader().open(header_path, data_path, raw=raw)
    except DataError as primary:
        # Size and file errors are conclusive; no alternate parser can waive them.
        if primary.code in ("SIZE_MISMATCH", "FILE_NOT_FOUND"):
            raise
        log.warning("envi_fallback", primary_error=primary.code)
        try:
            return FallbackEnviReader().open(header_path, data_path, raw=raw)
        except DataError as fallback:
            raise DataError(fallback.code, fallback.payload.detail, **fallback.payload.context, primary_error=primary.code) from fallback
