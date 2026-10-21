"""TASK-05 §5 R4/R5: extension, declared versions, Schema and pure execution."""
import json

import numpy as np
from pydantic import BaseModel, Field
import pytest

from spectrumagent.data import DataError
from spectrumagent.preprocess import OperatorRegistry
from spectrumagent.preprocess.schema import Params
from .conftest import run


def test_all_builtins_emit_pydantic_schema_and_reject_unknown_keys(registry):
    assert set(registry.entries) == {"reflectance","sg_smooth","sg_derivative","snv","msc","emsc","standardize","crop","resample","pca","mnf","ica","continuum"}
    for name, versions in registry.entries.items():
        assert list(versions) == [1]
        entry = versions[1]
        assert entry.params_schema == entry.model.model_json_schema()
        assert entry.params_schema["additionalProperties"] is False
        json.dumps(entry.params_schema,allow_nan=False)
        with pytest.raises(DataError) as caught:
            run(registry,name,[[1.,2.,3.]],{"unknown_key":True})
        assert caught.value.code == "INVALID_OPERATOR_PARAMS"
        assert any(item["field"].endswith("unknown_key") for item in caught.value.as_dict()["context"]["fields"])


@pytest.mark.parametrize("pipeline", [
    {"steps":[],"action":"x"}, {"step":[]}, {"steps":[{"op":"snv","params":{}}]},
    {"steps":[{"op":"snv","version":True,"params":{}}]},
    {"steps":[{"op":"snv","version":"1","params":{}}]},
    {"steps":[{"op":"snv","version":1,"params":{},"url":"http://x"}]},
    {"steps":[{"op":"snv","version":1,"params":[]}]}, "not json",
])
def test_pipeline_fixed_keys_required_types_structured(registry,pipeline):
    with pytest.raises(DataError) as caught:
        registry.run([[1.,2.,3.]],pipeline)
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
    assert all(set(item) == {"field","message"} for item in caught.value.as_dict()["context"]["fields"])
    json.dumps(caught.value.as_dict(),allow_nan=False)


def test_registered_schema_parse_execute_and_invalid_params_full_chain():
    class OffsetParams(Params):
        offset: float
    registry = OperatorRegistry()
    registry.register("offset",1,OffsetParams,lambda x,p:x+p["offset"])
    pipeline = json.dumps({"steps":[{"op":"offset","version":1,"params":{"offset":2.}},
                                    {"op":"offset","version":1,"params":{"offset":3.}}]})
    parsed = registry.parse_pipeline(pipeline)
    result = registry.run(np.array([[1.,2.]]),parsed)
    np.testing.assert_array_equal(result.spectra,[[6.,7.]])
    assert [step["params"]["offset"] for step in result.steps] == [2.,3.]
    assert all(step["meta"] == {} for step in result.steps)
    with pytest.raises(DataError) as caught:
        registry.run([[1.,2.]],{"steps":[{"op":"offset","version":1,"params":{"offset":"x"}}]})
    assert caught.value.code == "INVALID_OPERATOR_PARAMS"
    assert caught.value.as_dict()["context"]["fields"][0]["field"] == "steps.0.params.offset"


def test_same_name_multiversion_retained_and_stale_only_when_absent():
    registry = OperatorRegistry()
    class Empty(Params):
        pass
    registry.register("demo",1,Empty,lambda x,p:x+1)
    registry.register("demo",2,Empty,lambda x,p:x+2)
    x = np.array([[1.,2.,3.]])
    def pipeline(version):
        return {"steps":[{"op":"demo","version":version,"params":{}}]}
    for version in (1,2):
        a = registry.run(x,pipeline(version))
        b = registry.run(x,pipeline(version))
        np.testing.assert_allclose(a.spectra,x+version,rtol=0,atol=1e-12)
        np.testing.assert_array_equal(a.spectra,b.spectra)
    with pytest.raises(ValueError,match="不可覆盖"):
        registry.register("demo",1,Empty,lambda x,p:x+99)
    del registry.entries["demo"][1]  # Explicit retirement simulation; not a production endpoint.
    with pytest.raises(DataError) as caught:
        registry.run(x,pipeline(1))
    assert caught.value.code == "OPERATOR_VERSION_STALE" and caught.value.status_code == 409
    np.testing.assert_array_equal(registry.run(x,pipeline(2)).spectra,x+2)
    with pytest.raises(DataError) as unknown:
        registry.run(x,{"steps":[{"op":"never_registered","version":1,"params":{}}]})
    assert unknown.value.code == "OPERATOR_VERSION_STALE"


def test_two_return_forms_json_safe_meta_and_no_input_mutation():
    registry = OperatorRegistry()
    class Empty(Params):
        pass
    registry.register("matrix",1,Empty,lambda x,p:x*2)
    registry.register("meta",1,Empty,lambda x,p:(x+1,{"number":np.float64(2),"vector":np.array([1.,2.]),"nan":np.nan}))
    x = np.array([[1.,2.]])
    pipeline = {"steps":[{"op":name,"version":1,"params":{}} for name in ("matrix","meta")]}
    result = registry.run(x,pipeline)
    np.testing.assert_array_equal(x,[[1.,2.]])
    np.testing.assert_array_equal(result.spectra,[[3.,5.]])
    assert result.steps[0]["meta"] == {}
    assert result.steps[1]["meta"] == {"number":2.,"vector":[1.,2.],"nan":None}
    json.dumps(result.steps,allow_nan=False)


@pytest.mark.parametrize("name", ["reflectance","sg_smooth","sg_derivative","snv","msc","emsc"])
def test_operator_level_determinism_1e12_without_mutating_inputs(registry,reference,name):
    x = np.stack([reference,reference*2+.3])
    params = {"reflectance":{"hdr":{"reflectance scale factor":10}},
              "sg_smooth":{"window":5,"polyorder":2},
              "sg_derivative":{"window":5,"polyorder":2,"order":1},
              "snv":{},"msc":{"reference":reference},"emsc":{"reference":reference}}[name]
    before = x.copy()
    first = run(registry,name,x,params,random_state=0)
    second = run(registry,name,x,params,random_state=0)
    np.testing.assert_allclose(first.spectra,second.spectra,rtol=0,atol=1e-12)
    assert first.steps == second.steps
    np.testing.assert_array_equal(x,before)


def test_all_params_validated_before_any_impl_runs(registry, monkeypatch):
    called = []
    class Empty(Params):
        pass
    registry.register("probe",1,Empty,lambda x,p:called.append(True) or x)
    with pytest.raises(DataError):
        registry.run([[1.,2.,3.]],{"steps":[{"op":"probe","version":1,"params":{}},
                                         {"op":"sg_smooth","version":1,"params":{"window":4,"polyorder":2}}]})
    assert called == []


def test_new_operator_demo_is_local_registration_without_framework_changes():
    # §5 新增算子演示: this complete extension needs one small model + pure impl + registration.
    # It proves the extension seam; test runtime is not claimed as person-day measurement.
    class Gain(Params):
        gain: float = Field(gt=0)
    def amplify(spectra,params):
        return spectra*params["gain"]
    registry = OperatorRegistry()
    registry.register("demonstration_gain",1,Gain,amplify)
    pipeline = {"steps":[{"op":"demonstration_gain","version":1,"params":{"gain":2.}}]}
    np.testing.assert_array_equal(registry.run([[1.,3.]],pipeline).spectra,[[2.,6.]])
    assert registry.entries["demonstration_gain"][1].params_schema["properties"]["gain"]["exclusiveMinimum"] == 0


def test_registration_requires_forbid_schema_and_does_not_accept_arbitrary_schema_dict():
    class Open(BaseModel):
        value: float
    registry = OperatorRegistry()
    for model in (Open,{"type":"object"}):
        with pytest.raises(ValueError,match="BaseModel"):
            registry.register("bad",1,model,lambda x,p:x)
