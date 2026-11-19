"""TASK-05 11.1 pure operator framework; no IO, recipe DB or comparison engine."""
from . import operators, schema
from .registry import OperatorRegistry, OperatorVersionStale, PipelineResult, PreprocessError
from .operators.standardize import standardize
from .operators.crop import crop
from .operators.resample import resample
from .operators.pca import pca
from .operators.mnf import mnf
from .operators.ica import ica
from .operators.continuum import continuum


def builtin_registry():
    registry = OperatorRegistry()
    for name, model, impl in (
        ("reflectance", schema.ReflectanceParams, operators.reflectance),
        ("sg_smooth", schema.SmoothParams, operators.smooth),
        ("sg_derivative", schema.DerivativeParams, operators.derivative),
        ("snv", schema.SnvParams, operators.snv),
        ("msc", schema.MscParams, operators.msc),
        ("emsc", schema.EmscParams, operators.emsc),
        ("standardize", schema.StandardParams, standardize),
        ("crop", schema.CropParams, crop),
        ("resample", schema.ResampleParams, resample),
        ("pca", schema.PcaParams, pca),
        ("mnf", schema.MnfParams, mnf),
        ("ica", schema.IcaParams, ica),
        ("continuum", schema.ContinuumParams, continuum),
    ):
        registry.register(name, 1, model, impl)
    return registry


__all__ = ["builtin_registry", "OperatorRegistry", "OperatorVersionStale", "PipelineResult", "PreprocessError"]
