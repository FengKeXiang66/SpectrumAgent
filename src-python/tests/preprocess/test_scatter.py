"""TASK-05 §5 B04; R8 rank, exact zero scale, NaN detection and byte hashes."""
import hashlib
import json

import numpy as np
import pytest

from spectrumagent.data import DataError
from .conftest import run


def sha(array):
    return hashlib.sha256(np.ascontiguousarray(array,dtype=np.float64).tobytes()).hexdigest()


def test_snv_population_formula_and_metadata(registry):
    x = np.array([[1.,2.,7.],[3.,8.,9.]])
    result = run(registry,"snv",x)
    expected = (x-x.mean(axis=1,keepdims=True))/x.std(axis=1,keepdims=True,ddof=0)
    np.testing.assert_array_equal(result.spectra,expected)
    assert result.steps[0]["meta"] == {"method":"snv","reference_sha256":None,"reference_len":None,"std_ddof":0,"zero_std_count":0}
    assert not np.allclose(result.spectra, (x-x.mean(axis=1,keepdims=True))/x.std(axis=1,keepdims=True,ddof=1))


@pytest.mark.parametrize("policy", ["zeros","nan","error"])
def test_snv_zero_variance_policies(registry, policy):
    x = np.array([[2.,2.,2.],[1.,2.,3.]])
    if policy == "error":
        with pytest.raises(DataError) as caught:
            run(registry,"snv",x,{"zero_std":policy})
        assert caught.value.code == "SCATTER_MODEL_DEGENERATE"
    else:
        result = run(registry,"snv",x,{"zero_std":policy})
        assert (np.all(result.spectra[0] == 0) if policy == "zeros" else np.isnan(result.spectra[0]).all())
        assert result.steps[0]["meta"]["zero_std_count"] == 1


def test_snv_default_zeros_does_not_replace_nan_input(registry):
    result = run(registry,"snv",[[2.,2.,2.],[1.,np.nan,3.]])
    assert np.all(result.spectra[0] == 0) and np.isnan(result.spectra[1]).all()
    assert result.steps[0]["meta"]["zero_std_count"] == 1


@pytest.mark.parametrize("method,order", [("msc",0),("emsc",2),("emsc",1)])
def test_explicit_reference_lstsq_formula_coefficient_fingerprints(registry, reference, method, order):
    t = np.linspace(0.,1.,len(reference))
    design = np.column_stack([reference,np.ones(len(t)),*[t**k for k in range(1,order+1)]])
    chosen = np.array([[2.,.7,*([.3,-.2][:order])],[.5,-.3,*([-.4,.6][:order])]])
    x = chosen @ design.T
    params = {"reference":reference, **({"polynomial_order":order} if method == "emsc" else {})}
    result = run(registry,method,x,params)
    np.testing.assert_allclose(result.spectra,np.broadcast_to(reference,x.shape),rtol=0,atol=1e-12)
    coefficients = np.stack([np.linalg.lstsq(design,row,rcond=None)[0] for row in x])
    meta = result.steps[0]["meta"]
    assert meta["reference_sha256"] == sha(reference) and meta["reference_len"] == len(reference)
    assert meta["coefficients_shape"] == [2,order+2] and meta["coefficients_sha256"] == sha(coefficients)
    assert "coefficients" not in meta and "reference_source" not in meta
    assert meta["zero_scale_count"] == meta["nan_spectra"] == 0
    assert meta["std_ddof"] is None and meta["zero_std_count"] == 0
    if method == "emsc":
        assert meta["emsc_order"] == order
    json.dumps(result.steps,allow_nan=False)


@pytest.mark.parametrize("method", ["msc","emsc"])
def test_reference_is_required_never_current_input_mean(registry, method):
    with pytest.raises(DataError) as caught:
        run(registry,method,[[1.,2.,3.,4.,5.]])
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"


@pytest.mark.parametrize("method,columns", [("msc",2),("emsc",4)])
def test_rank_deficiency_400_with_required_context(registry, method, columns):
    with pytest.raises(DataError) as caught:
        run(registry,method,np.ones((2,7)),{"reference":np.ones(7)})
    assert caught.value.code == "SCATTER_MODEL_DEGENERATE" and caught.value.status_code == 400
    assert caught.value.as_dict()["context"] == {"design_rank":columns-1,"expected_columns":columns}


@pytest.mark.parametrize("method", ["msc","emsc"])
def test_nan_rows_detected_without_passing_nan_to_lapack(registry, reference, method, monkeypatch):
    actual = np.linalg.lstsq
    def checked(design, target, **kwargs):
        assert not np.isnan(design).any() and not np.isnan(target).any()
        return actual(design,target,**kwargs)
    monkeypatch.setattr(np.linalg,"lstsq",checked)
    x = np.stack([reference,reference.copy()])
    x[1,4] = np.nan
    result = run(registry,method,x,{"reference":reference})
    assert np.isnan(result.spectra[1]).all() and np.isfinite(result.spectra[0]).all()
    assert result.steps[0]["meta"]["nan_spectra"] == 1
    assert result.steps[0]["meta"]["zero_scale_count"] == 0
    json.dumps(result.steps,allow_nan=False)


@pytest.mark.parametrize("scale", [0.,np.nan,1e-30])
def test_exact_zero_or_nan_scale_only_no_epsilon_policy(registry, reference, monkeypatch, scale):
    original = np.linalg.lstsq
    def injected(design,target,**kwargs):
        result = original(design,target,**kwargs)
        if np.any(target):
            result[0][0] = scale
        return result
    monkeypatch.setattr(np.linalg,"lstsq",injected)
    result = run(registry,"msc",reference[None,:],{"reference":reference})
    invalid = scale == 0. or np.isnan(scale)
    assert result.steps[0]["meta"]["zero_scale_count"] == int(invalid)
    assert (np.isnan(result.spectra).all() if invalid else np.isfinite(result.spectra).all())
    assert "coefficients" not in result.steps[0]["meta"]


def test_real_zero_target_and_default_emsc_order(registry, reference):
    result = run(registry,"emsc",np.zeros((1,len(reference))),{"reference":reference})
    assert np.isnan(result.spectra).all()
    assert result.steps[0]["meta"]["zero_scale_count"] == 1 and result.steps[0]["meta"]["emsc_order"] == 2
