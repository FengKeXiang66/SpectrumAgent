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
