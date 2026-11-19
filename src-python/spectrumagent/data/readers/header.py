"""One ENVI vocabulary, normalizer, classic brace parser and exact size gate."""
from dataclasses import dataclass
import math
from pathlib import Path
import re

import numpy as np
import structlog

from ..errors import DataError

log = structlog.get_logger("datasets.header")
CODES = {1: "u1", 2: "i2", 3: "i4", 4: "f4", 5: "f8", 6: "c8", 9: "c16", 12: "u2", 13: "u4", 14: "i8", 15: "u8"}
ALIASES = {"datatype": "data_type", "byteorder": "byte_order", "headeroffset": "header_offset", "wavelength": "wavelengths", "wavelengths": "wavelengths", "reflectancescalefactor": "scale_factor", "scalefactor": "scale_factor", "datafile": "data_file"}
KNOWN = {"samples", "lines", "bands", "data_type", "interleave", "byte_order", "header_offset", "wavelengths", "fwhm", "scale_factor", "data_file"}
EXTENSIONS = (".bin", ".raw", ".dat", ".img", ".bsq", ".bil", ".bip", "")


def key_name(key):
    if not isinstance(key, str):
        raise DataError("HEADER_INVALID", "头字段名称必须是字符串")
    compact = re.sub(r"[\s_]", "", key).lower()
    return ALIASES.get(compact, compact)


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise DataError("FILE_NOT_FOUND", "头文件不存在", path=str(path)) from exc
    except (OSError, UnicodeError) as exc:
        raise DataError("HEADER_INVALID", "头文件不可读或不是UTF-8", path=str(path)) from exc


def classic(text: str, *, magic=True) -> dict:
    lines = text.splitlines()
    if magic:
        if not lines or lines.pop(0).strip().upper() != "ENVI":
            raise DataError("ENVI_NOT_STANDARD", "缺少ENVI魔术行，需非标准头兜底")
    result = {}
    pending = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        pending += ("\n" if pending else "") + line
        if pending.count("{") > pending.count("}"):
            continue
        if "=" not in pending or pending.count("{") != pending.count("}"):
            raise DataError("HEADER_INVALID", "头字段必须为key=value，花括号必须配对")
        name, _, value = pending.partition("=")
        name, value = name.strip(), value.strip()
        if not name or not value or name in result:
            raise DataError("HEADER_INVALID", "空字段或重复头字段")
        result[name] = [v.strip() for v in value[1:-1].split(",")] if value.startswith("{") and value.endswith("}") else value.strip('"')
        pending = ""
    if pending:
        raise DataError("HEADER_INVALID", "跨行花括号未闭合")
    return result


def integer(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise DataError("HEADER_INVALID", "字段必须为整数", field=name)
    try:
        n = int(value)
    except ValueError as exc:
        raise DataError("HEADER_INVALID", "字段必须为整数", field=name) from exc
    if n < minimum:
        raise DataError("HEADER_INVALID", "字段低于合法下限", field=name)
    return n


@dataclass(frozen=True)
class Header:
    shape: tuple[int, int, int]
    dtype: np.dtype
    interleave: str
    offset: int
    wavelengths: list[float]
    fwhm: list[float] | None
    scale: float
    data_file: str | None
    metadata: dict


def normalize(fields: dict, *, require_interleave=False) -> Header:
    if not isinstance(fields, dict):
        raise DataError("HEADER_INVALID", "头必须为对象")
    values, metadata = {}, {}
    for key, value in fields.items():
        name = key_name(key)
        if name in values:
            raise DataError("HEADER_INVALID", "规范化后出现重复字段", field=name)
        values[name] = value
        if name not in KNOWN:
            metadata[key] = value
            log.warning("unknown_header_key", key=key)
    for name in ("samples", "lines", "bands", "data_type"):
        if name not in values:
            raise DataError("HEADER_INVALID", "缺少必填头字段", field=name)
    shape = tuple(integer(values[n], n, 1) for n in ("lines", "samples", "bands"))
    if "interleave" not in values:
        if require_interleave:
            raise DataError("ENVI_NOT_STANDARD", "缺少interleave，需BSQ兜底")
        log.warning("default_interleave", interleave="bsq")
    interleave = str(values.get("interleave", "bsq")).lower()
    if interleave not in ("bsq", "bil", "bip"):
        raise DataError("HEADER_INVALID", "interleave必须为bsq/bil/bip")
    raw_dtype = values["data_type"]
    try:
        if isinstance(raw_dtype, bool) or not isinstance(raw_dtype, (str, int)):
            raise ValueError("boolean dtype")
        if isinstance(raw_dtype, int) or (isinstance(raw_dtype, str) and raw_dtype.isdecimal()):
            dtype = np.dtype(CODES[int(raw_dtype)])
        else:
            dtype = np.dtype(raw_dtype)
        if dtype.kind not in "iufc" or dtype.hasobject:
            raise ValueError("non-numeric dtype")
    except (TypeError, ValueError, KeyError) as exc:
        raise DataError("HEADER_INVALID", "不支持的data_type") from exc
    byte_order = values.get("byte_order", 0)
    order = str(byte_order).lower()
    if isinstance(byte_order, bool) or order not in ("0", "1", "little", "big"):
        raise DataError("HEADER_INVALID", "byte_order必须为0/1或little/big")
    dtype = dtype.newbyteorder("<" if order in ("0", "little") else ">")
    offset = integer(values.get("header_offset", 0), "header_offset")
    def numeric_list(name):
        if name not in values:
            return None
        source = values[name]
        if not isinstance(source, list) or len(source) != shape[2] or any(isinstance(v, bool) for v in source):
            raise DataError("HEADER_INVALID", "波段元数据长度必须等于bands", field=name)
        try:
            result = [float(v) for v in source]
        except (ValueError, TypeError) as exc:
            raise DataError("HEADER_INVALID", "波段元数据必须是数字列表", field=name) from exc
        if not all(math.isfinite(v) for v in result):
            raise DataError("HEADER_INVALID", "波段元数据必须是有限数字", field=name)
        return result
    try:
        scale = float(values.get("scale_factor", 1.0))
        if isinstance(values.get("scale_factor"), bool) or not math.isfinite(scale) or scale <= 0:
            raise ValueError("nonpositive scale")
    except (ValueError, TypeError) as exc:
        raise DataError("HEADER_INVALID", "scale_factor必须为有限正数") from exc
    data_file = values.get("data_file")
    if data_file is not None and (not isinstance(data_file, str) or not data_file.strip()):
        raise DataError("HEADER_INVALID", "data_file必须是非空路径字符串")
    return Header(shape, dtype, interleave, offset, numeric_list("wavelengths") or [], numeric_list("fwhm"), scale, data_file, metadata)


def resolve_data(header_path: Path, header: Header, explicit=None) -> Path:
    candidate = Path(explicit) if explicit is not None else Path(header.data_file) if header.data_file else None
    if candidate is not None:
        candidate = candidate if candidate.is_absolute() else header_path.parent / candidate
    else:
        stem = header_path.with_suffix("")
        candidate = next((Path(str(stem) + ext) for ext in EXTENSIONS if Path(str(stem) + ext).is_file()), None)
    if candidate is None or not candidate.is_file():
        raise DataError("FILE_NOT_FOUND", "无法关联数据文件", path=str(candidate or header_path))
    return candidate.resolve()


def validate_size(path: Path, header: Header):
    expected = header.offset + math.prod(header.shape) * header.dtype.itemsize
    try:
        actual = path.stat().st_size
    except OSError as exc:
        raise DataError("FILE_NOT_FOUND", "数据文件不可读", path=str(path)) from exc
    if actual != expected:
        raise DataError("SIZE_MISMATCH", "头声明大小与数据文件大小不一致", expected_bytes=expected, actual_bytes=actual, path=str(path))
