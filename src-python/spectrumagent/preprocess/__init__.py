"""TASK-05 11.1 pure operator framework; no IO, recipe DB or comparison engine."""
from . import operators, schema
from .registry import OperatorRegistry, OperatorVersionStale, PipelineResult, PreprocessError


def builtin_registry():
    registry = OperatorRegistry()
    for name, model, impl in (
        ("reflectance", schema.ReflectanceParams, operators.reflectance),
        ("sg_smooth", schema.SmoothParams, operators.smooth),
        ("sg_derivative", schema.DerivativeParams, operators.derivative),
        ("snv", schema.SnvParams, operators.snv),
        ("msc", schema.MscParams, operators.msc),
        ("emsc", schema.EmscParams, operators.emsc),
    ):
        registry.register(name, 1, model, impl)
    return registry


__all__ = ["builtin_registry", "OperatorRegistry", "OperatorVersionStale", "PipelineResult", "PreprocessError"]
