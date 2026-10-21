"""R8: Pydantic models are the sole parameter validator and Schema source."""
from typing import Annotated, Any, Literal

import numpy as np
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, FiniteFloat, JsonValue, ValidationInfo, field_validator


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


def vector(value):
    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise ValueError("参考谱必须为一维")
        return value.tolist()
    return value


Vector = Annotated[list[float], BeforeValidator(vector), Field(min_length=1)]
FiniteVector = Annotated[list[FiniteFloat], BeforeValidator(vector), Field(min_length=1)]


class ReflectanceParams(Params):
    hdr: dict[str, JsonValue]
    branch: Literal["reference", "scale", "passthrough"] | None = None
    white_reference: Vector | None = None
    dark_reference: Vector | None = None
    guard: Literal["clip", "keep", "error"] = "clip"


class SmoothParams(Params):
    window: Annotated[int, Field(gt=0)]
    polyorder: Annotated[int, Field(ge=0)]
    mode: Literal["interp", "mirror", "constant", "nearest", "wrap"] = "interp"

    @field_validator("window")
    @classmethod
    def odd_window(cls, value):
        if value % 2 == 0:
            raise ValueError("window 必须为奇数")
        return value

    @field_validator("polyorder")
    @classmethod
    def polynomial_fits(cls, value, info: ValidationInfo):
        # R7 overrides the earlier card typo: scipy requires STRICTLY less.
        if "window" in info.data and value >= info.data["window"]:
            raise ValueError("polyorder 必须严格小于 window")
        return value


class DerivativeParams(SmoothParams):
    order: Annotated[int, Field(ge=1, le=2)]


class SnvParams(Params):
    zero_std: Literal["zeros", "nan", "error"] = "zeros"


class MscParams(Params):
    reference: FiniteVector


class EmscParams(MscParams):
    polynomial_order: Annotated[int, Field(ge=0)] = 2


class Step(Params):
    op: Annotated[str, Field(min_length=1)]
    version: Annotated[int, Field(gt=0)]
    params: dict[str, Any]


class Pipeline(Params):
    steps: list[Step]


class StandardParams(Params):
    method: Literal["standard", "minmax", "area", "vector"]
    zero_std: Literal["zeros", "nan", "error"] = "zeros"


class CropParams(Params):
    source: FiniteVector
    range: tuple[float, float]

    @field_validator("source")
    @classmethod
    def increasing_source(cls, value):
        if not np.all(np.diff(value) > 0):
            raise ValueError("source 必须严格递增")
        return value

    @field_validator("range", mode="before")
    @classmethod
    def json_pair(cls, value):
        # JSON represents a two-element tuple as an array.
        return tuple(value) if isinstance(value, list) else value

    @field_validator("range")
    @classmethod
    def ordered_range(cls, value):
        if not value[0] < value[1]:
            raise ValueError("range 须满足 lo < hi")
        return value


class ResampleParams(Params):
    source: FiniteVector
    target: FiniteVector
    method: Literal["linear", "spline"]

    @field_validator("source", "target")
    @classmethod
    def increasing_axis(cls, value):
        if len(value) < 2 or not np.all(np.diff(value) > 0):
            raise ValueError("source/target 须严格递增且至少两波段，以定义相邻间隔代理值")
        return value
