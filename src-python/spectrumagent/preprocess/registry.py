"""Version-addressed pure operators; no recipe storage, HTTP, or cube reading."""
from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Callable

import numpy as np
from pydantic import BaseModel, ValidationError

from spectrumagent.data import DataError
from .schema import Pipeline


class PreprocessError(DataError):
    status_code = 400


class OperatorVersionStale(PreprocessError):
    status_code = 409

    def __init__(self, name, version):
        super().__init__("OPERATOR_VERSION_STALE", "声明的算子版本不存在；该 version 已退役或未注册，旧配方不可复现",
                         op=name, version=version)


def invalid(field, message):
    return PreprocessError("INVALID_OPERATOR_PARAMS", "算子参数校验失败",
                           fields=[{"field": field, "message": message}])


def validate(model, value, prefix):
    try:
        return model.model_validate(value)
    except ValidationError as error:
        fields = [{"field": ".".join([prefix, *map(str, item["loc"])]), "message": item["msg"]}
                  for item in error.errors()]
        raise PreprocessError("INVALID_OPERATOR_PARAMS", "算子参数校验失败", fields=fields) from error


def json_safe(value):
    """Strict JSON metadata only; never replace NaNs in the spectral matrix."""
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("metadata keys must be strings")
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("metadata must be JSON-safe")


@dataclass(frozen=True)
class OperatorEntry:
    version: int
    model: type[BaseModel]
    impl: Callable

    @property
    def params_schema(self):
        return self.model.model_json_schema()


@dataclass
class PipelineResult:
    spectra: np.ndarray
    wavelengths: np.ndarray | None
    steps: list[dict]


class OperatorRegistry:
    def __init__(self):
        self.entries: dict[str, dict[int, OperatorEntry]] = {}

    def register(self, name, version, model, impl):
        if not isinstance(name, str) or not name or type(version) is not int or version < 1:
            raise ValueError("注册须给出非空 name 与正整数 version")
        if not isinstance(model, type) or not issubclass(model, BaseModel) or model.model_config.get("extra") != "forbid":
            raise ValueError("params 模型必须为 extra='forbid' 的 BaseModel")
        if not callable(impl):
            raise ValueError("impl 必须可调用")
        if version in self.entries.get(name, {}):
            raise ValueError("同名同版本不可覆盖；实现变更必须注册新 version")
        model.model_json_schema()  # Fail at registration if Schema cannot be emitted.
        self.entries.setdefault(name, {})[version] = OperatorEntry(version, model, impl)

    def resolve(self, name, version):
        entry = self.entries.get(name, {}).get(version)
        if entry is None:
            raise OperatorVersionStale(name, version)
        return entry

    def parse_pipeline(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError) as error:
                raise invalid("pipeline", "pipeline 必须为合法 JSON") from error
        if isinstance(value, Pipeline):
            value = value.model_dump()
        pipeline = validate(Pipeline, value, "pipeline")
        for i, step in enumerate(pipeline.steps):
            entry = self.resolve(step.op, step.version)
            validate(entry.model, step.params, f"steps.{i}.params")
        return pipeline

    def run(self, spectra, pipeline, *, wavelengths=None, random_state=None):
        """random_state is reserved for 11.3; these operators are deterministic."""
        pipeline = self.parse_pipeline(pipeline)
        array = np.asarray(spectra)
        if array.ndim != 2 or 0 in array.shape or array.dtype.kind not in "iuf":
            raise invalid("spectra", "需要非空实数谱矩阵 (n_spectra,bands)")
        axis = None if wavelengths is None else np.asarray(wavelengths).copy()
        if axis is not None and (axis.ndim != 1 or len(axis) != array.shape[1]):
            raise invalid("wavelengths", "波长轴长度必须等于 bands")
        result = array.copy()
        records = []
        for i, step in enumerate(pipeline.steps):
            entry = self.resolve(step.op, step.version)
            params = validate(entry.model, step.params, f"steps.{i}.params").model_dump()
            output = entry.impl(result, deepcopy(params))
            output, meta = output if isinstance(output, tuple) and len(output) == 2 else (output, {})
            output = np.asarray(output)
            if output.shape != result.shape or output.dtype.kind not in "iuf" or not isinstance(meta, dict):
                raise PreprocessError("INVALID_OPERATOR_RESULT", "算子须返回同形实数谱矩阵和可选 meta 字典", op=step.op)
            try:
                record = json_safe({"op": step.op, "version": step.version, "params": params, "meta": meta})
            except TypeError as error:
                raise PreprocessError("INVALID_OPERATOR_RESULT", "算子 meta 无法安全序列化为 JSON", op=step.op) from error
            records.append(record)
            result = output
        return PipelineResult(result, axis, records)
