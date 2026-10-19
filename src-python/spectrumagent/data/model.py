"""Metadata schema and bounded access, always indexed (lines, samples, bands)."""
from dataclasses import field
from typing import Annotated, Callable, Literal, Protocol

import numpy as np
from pydantic import ConfigDict, Field, JsonValue, TypeAdapter, field_validator, model_validator
from pydantic.dataclasses import dataclass

from .errors import DataError

Dimension = Annotated[int, Field(strict=True, gt=0)]
Finite = Annotated[float, Field(allow_inf_nan=False)]


class CubeAccess(Protocol):
    def read(self, rows: list[int], columns: list[int], bands: list[int]) -> np.ndarray: ...
    def asarray(self) -> np.memmap: ...


class MemmapAccess:
    """A read-only factory; mapping is created on first explicit access, never load()."""
    def __init__(self, factory: Callable[[], np.memmap]):
        self.factory = factory
        self._array: np.memmap | None = None

    def asarray(self) -> np.memmap:
        if self._array is None:
            self._array = self.factory()
        return self._array

    def read(self, rows, columns, bands):
        return self.asarray()[np.ix_(rows, columns, bands)]


@dataclass(config=ConfigDict(extra="forbid", allow_inf_nan=False), frozen=True)
class SpectrumDataSet:
    name: str
    shape: tuple[Dimension, Dimension, Dimension]
    dtype: str
    interleave: Literal["bsq", "bil", "bip"]
    wavelengths: list[Finite]
    data_path: str
    header_path: str
    fwhm: list[Finite] | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    @field_validator("dtype")
    @classmethod
    def valid_dtype(cls, value):
        try:
            dtype = np.dtype(value)
        except TypeError as exc:
            raise ValueError("dtype必须是numpy数值类型") from exc
        if dtype.kind not in "iufc":
            raise ValueError("dtype必须是numpy数值类型")
        return dtype.name

    @model_validator(mode="after")
    def band_metadata(self):
        if self.wavelengths and len(self.wavelengths) != self.shape[2]:
            raise ValueError("wavelengths长度必须等于bands；未知波长用空列表")
        if self.fwhm is not None and len(self.fwhm) != self.shape[2]:
            raise ValueError("fwhm长度必须等于bands；未知fwhm用null")
        return self

    def bind(self, access: CubeAccess, *, raw: bool = False, scale_factor: float = 1.0):
        if not np.isfinite(scale_factor) or scale_factor <= 0:
            raise DataError("HEADER_INVALID", "scale_factor必须是有限正数")
        # Runtime bindings are deliberately not dataclass fields or serialized data.
        object.__setattr__(self, "_access", access)
        object.__setattr__(self, "_raw", raw)
        object.__setattr__(self, "_scale", float(scale_factor))
        return self

    def _indices(self, values, axis: int):
        result = list(values)
        if not result or any(type(i) is not int or not 0 <= i < self.shape[axis] for i in result):
            raise DataError("INVALID_INDEX", "索引越界或类型非法", axis=axis)
        return result

    def _read(self, rows, columns, bands):
        rows, columns, bands = (self._indices(values, axis) for axis, values in enumerate((rows, columns, bands)))
        access = getattr(self, "_access", None)
        if access is None:
            raise DataError("DATA_NOT_BOUND", "数据集未绑定读取器")
        try:
            result = access.read(rows, columns, bands)
            if getattr(self, "_raw", False):
                return result
            return np.asarray(result, dtype=np.float64) / self._scale
        except DataError:
            raise
        except (OSError, ValueError, IndexError, EOFError) as exc:
            raise DataError("READ_FAILED", "读取数据失败", reason=type(exc).__name__) from exc

    def read_band(self, i: int):
        return self._read(range(self.shape[0]), range(self.shape[1]), [i])[:, :, 0]

    def read_bands(self, indices: list[int]):
        """Return (lines, samples, n), with bands on the last axis."""
        return self._read(range(self.shape[0]), range(self.shape[1]), indices)

    def read_pixel(self, row: int, col: int):
        return self._read([row], [col], range(self.shape[2]))[0, 0, :]

    def read_region(self, l0: int, l1: int, s0: int, s1: int):
        if any(type(i) is not int for i in (l0, l1, s0, s1)) or not (0 <= l0 < l1 <= self.shape[0] and 0 <= s0 < s1 <= self.shape[1]):
            raise DataError("INVALID_INDEX", "区域必须为有效的左闭右开边界")
        return self._read(range(l0, l1), range(s0, s1), range(self.shape[2]))

    def read_subregion(self, row_bounds: tuple[int, int], col_bounds: tuple[int, int]):
        """Read all bands in the explicit half-open region."""
        return self.read_region(*row_bounds, *col_bounds)

    def read_subimage(self, rows: list[int], columns: list[int], bands: list[int]):
        return self._read(rows, columns, bands)

    def to_numpy(self) -> np.memmap:
        """raw模式：DN原值，未除scale factor；反射率需自行/65535（塑料样本）。

        返回(lines,samples,bands)的零拷贝memmap视图，保持源dtype。
        缩放模式禁止隐式全量物化；使用有界read_*接口。
        """
        if not getattr(self, "_raw", False):
            raise DataError("FULL_ARRAY_DISABLED", "缩放模式不提供全量数组接口（禁止隐式全量读取）；请用read_band/read_bands/read_pixel/read_subregion等有界接口")
        try:
            array = self._access.asarray()
            if not isinstance(array, np.memmap):
                raise DataError("READ_FAILED", "raw读取器必须返回np.memmap")
            return array
        except DataError:
            raise
        except (OSError, ValueError, EOFError) as exc:
            raise DataError("READ_FAILED", "映射数据失败", reason=type(exc).__name__) from exc

    def as_dict(self):
        return TypeAdapter(SpectrumDataSet).dump_python(self, mode="json")

    @classmethod
    def json_schema(cls):
        return TypeAdapter(cls).json_schema()
