"""Frozen advanced-recipe transforms shared by training and deployment."""
from copy import deepcopy
import json

import numpy as np

from spectrumagent.data import DataError
from . import builtin_registry
from .operators.pca import transform as linear_transform
from .registry import PreprocessError, effective_pipeline, validate

TRAINING_OPERATORS = frozenset({'sg_smooth', 'sg_derivative', 'snv', 'standardize',
                                'crop', 'resample', 'pca', 'mnf', 'ica', 'continuum'})


def fit(spectra, pipeline, *, wavelengths=None, sample_ids):
    """Fit only the supplied training population using existing v1 kernels."""
    x = finite(np.asarray(spectra, dtype=np.float64))
    if x.ndim != 2 or not len(x) or x.shape[1] == 0 or len(sample_ids) != len(x):
        raise PreprocessError('INVALID_TRAINING_INPUT', '训练谱与样品编号须等长且非空')
    definition = effective_pipeline(pipeline)
    axis = None if wavelengths is None or len(wavelengths) == 0 else np.asarray(wavelengths, dtype=float)
    if axis is not None and (axis.shape != (x.shape[1],) or not np.isfinite(axis).all()):
        raise PreprocessError('WAVELENGTH_AXIS_MISMATCH', '训练输入波长轴无效')
    operators, records, current = builtin_registry(), [], x
    for step in definition['steps']:
        op, params = step['op'], step['params']
        if op not in TRAINING_OPERATORS or step['version'] != 1:
            raise PreprocessError('STRICT_PREPROCESS_UNSUPPORTED', '严格回归尚不支持该算子或参考来源', op=op)
        if op in {'crop', 'resample'} and (axis is None or not np.array_equal(params['source'], axis)):
            raise PreprocessError('WAVELENGTH_AXIS_MISMATCH', '裁剪或重采样须绑定当前物理波长轴', op=op)
        if op in {'pca', 'mnf', 'ica'} and params['n_components'] > min(len(x)-1, current.shape[1]):
            raise PreprocessError('INVALID_COMPONENT_COUNT', '降维分量不得超过训练样品数减一及当前特征数', op=op)
        result = operators.run(current, {'steps': [step]}, wavelengths=axis)
        single = {'protocol': 1, 'pipeline': {'steps': [step]}, 'steps': result.steps,
                  'input_n_features': current.shape[1]}
        replay = transform(single, single['pipeline'], current)
        if not np.allclose(replay, finite(result.spectra), rtol=1e-10, atol=1e-12):
            raise mismatch()
        # Subsequent fit steps see exactly the same transform arithmetic as
        # validation and deployment, including row-wise matrix multiplication.
        current, axis = replay, result.wavelengths
        records.extend(result.steps)
    state = {'protocol': 1, 'pipeline': definition, 'steps': records, 'input_n_features': x.shape[1],
             'output_n_features': current.shape[1], 'fit_sample_ids': list(sample_ids),
             'output_wavelengths': None if axis is None else axis.tolist()}
    # All predictions, including training, use exactly the deployed row order.
    replay = transform(state, definition, x)
    if not np.allclose(replay, current, rtol=1e-10, atol=1e-12):
        raise mismatch()
    return state


def mismatch():
    return PreprocessError("CALIBRATION_MISMATCH", "标定缺失、维度或算子版本与配方不一致")


def finite(value):
    if not np.isfinite(value).all():
        raise PreprocessError("NON_FINITE_SPECTRA", "输入谱或变换结果含非有限数值")
    return value


def transform(calibration, pipeline, block):
    """Never call a fit entry for any of the five cross-sample fitted operators.

    Fixed one-row matrix transforms also avoid BLAS batch-size rounding changes.
    """
    result = finite(np.asarray(block, dtype=np.float64))
    if result.ndim != 2 or 0 in result.shape:
        raise PreprocessError("FEATURE_COUNT_MISMATCH", "需要非空二维像素谱")
    operators = builtin_registry()
    try:
        expected = effective_pipeline(pipeline)
        if (calibration["protocol"] != 1 or calibration["pipeline"] != expected
                or result.shape[1] != calibration["input_n_features"]
                or len(calibration["steps"]) != len(expected["steps"])):
            raise mismatch()
        for step, saved in zip(operators.parse_pipeline(pipeline).steps, calibration["steps"]):
            entry = operators.resolve(step.op, step.version)
            params = json.loads(json.dumps(validate(entry.model, step.params, "params").model_dump()))
            if any(saved.get(key) != value for key, value in
                   (("op", step.op), ("version", step.version), ("params", params))):
                raise mismatch()
            meta = saved["meta"]
            if step.op == "standardize" and params["method"] in ("standard", "minmax"):
                fitted = meta["fitted"]
                if len(fitted) != result.shape[1]:
                    raise mismatch()
                if params["method"] == "standard":
                    offset = np.asarray([row["mean"] for row in fitted])
                    scale = np.asarray([row["std"] for row in fitted])
                else:
                    offset = np.asarray([row["min"] for row in fitted])
                    scale = np.asarray([row["max"] for row in fitted]) - offset
                if not np.isfinite(offset).all() or not np.isfinite(scale).all() or np.any(scale < 0):
                    raise mismatch()
                zero = scale == 0
                if zero.any() and params["zero_std"] == "error":
                    raise mismatch()
                with np.errstate(divide="ignore", invalid="ignore"):
                    result = (result - offset) / scale
                if zero.any():
                    result[:, zero] = 0.0 if params["zero_std"] == "zeros" else np.nan
            elif step.op in ("pca", "mnf", "ica"):
                mean, loadings = np.asarray(meta["mean"]), np.asarray(meta["loadings"])
                if (mean.shape != (result.shape[1],) or loadings.ndim != 2
                        or loadings.shape[0] != result.shape[1] or loadings.shape[1] == 0
                        or not np.isfinite(mean).all() or not np.isfinite(loadings).all()):
                    raise mismatch()
                result = np.concatenate([linear_transform(row[None, :], mean, loadings) for row in result])
            else:
                # These entries operate per spectrum; fixed row calls make the
                # numerical result independent of the outer IO block size.
                outputs = []
                for row in result:
                    output = entry.impl(row[None, :], deepcopy(params))
                    outputs.append(output[0] if isinstance(output, tuple) else output)
                result = np.concatenate(outputs)
            if result.ndim != 2 or result.shape[0] != len(block) or 0 in result.shape:
                raise mismatch()
            finite(result)
    except PreprocessError:
        raise
    except (DataError, KeyError, TypeError, ValueError, IndexError) as error:
        raise mismatch() from error
    return result

