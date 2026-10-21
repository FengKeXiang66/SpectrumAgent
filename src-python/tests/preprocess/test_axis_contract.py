"""R9 contract independently exercised with registered extension operators."""
import hashlib
import json

import numpy as np
import pytest

from spectrumagent.data import DataError
from spectrumagent.preprocess.schema import Params


def test_crop_then_resample_final_axis_and_summary_only(registry):
    pipeline = {"steps":[{"op":"crop","version":1,"params":{"source":[400.,500.,600.,700.,800.],"range":[500.,700.]}},
                         {"op":"resample","version":1,"params":{"source":[500.,600.,700.],"target":[500.,550.,600.,650.,700.],"method":"linear"}}]}
    x = np.array([[0.,1.,2.,3.,4.],[10.,11.,12.,13.,14.]])
    for axis in (None,[1.,2.,3.,4.,5.]):
        result = registry.run(x,pipeline,wavelengths=axis)
        np.testing.assert_allclose(result.spectra,[[1.,1.5,2.,2.5,3.],[11.,11.5,12.,12.5,13.]],rtol=0,atol=1e-12)
        np.testing.assert_array_equal(result.wavelengths,[500.,550.,600.,650.,700.])
        for step, expected in zip(result.steps,([500.,600.,700.],[500.,550.,600.,650.,700.])):
            meta = step["meta"]
            assert "axis" not in meta and "axis" not in step
            assert meta["axis_len"] == len(expected)
            assert meta["axis_sha256"] == hashlib.sha256(np.array(expected,dtype=np.float64).tobytes()).hexdigest()
        json.dumps(result.steps,allow_nan=False)


@pytest.mark.parametrize("axis", [None,[10.,20.,30.]])
def test_changed_bands_without_axis_always_rejected(registry,axis):
    registry.register("audit_missing",1,Params,lambda x,p:x[:,:2])
    with pytest.raises(DataError) as caught:
        registry.run([[1.,2.,3.]],{"steps":[{"op":"audit_missing","version":1,"params":{}}]},wavelengths=axis)
    assert caught.value.code == "INVALID_OPERATOR_RESULT"
    assert caught.value.as_dict()["context"] == {"op":"audit_missing","reason":"缺少 meta.axis"}


@pytest.mark.parametrize("output", [np.ones((2,3)),np.ones(3),np.empty((1,0)),np.ones((1,3),dtype=complex),np.ones((1,3),dtype=bool)])
def test_rows_rank_empty_or_nonreal_output_rejected(registry,output):
    registry.register("bad_shape",1,Params,lambda x,p:output)
    with pytest.raises(DataError) as caught:
        registry.run([[1.,2.,3.]],{"steps":[{"op":"bad_shape","version":1,"params":{}}]})
    assert caught.value.code == "INVALID_OPERATOR_RESULT"
    assert "谱条数不可变、bands 可变" in str(caught.value)


@pytest.mark.parametrize("axis", [[1.,1.],[2.,1.],[1.,np.nan],[1.,np.inf],[1.],[[1.,2.]],["x","y"]])
def test_declared_axis_validated_before_records(registry,axis):
    registry.register("bad_axis",1,Params,lambda x,p:(x[:,:2],{"axis":axis}))
    with pytest.raises(DataError) as caught:
        registry.run([[1.,2.,3.]],{"steps":[{"op":"bad_axis","version":1,"params":{}}]})
    assert caught.value.code == "INVALID_OPERATOR_RESULT"
    context = caught.value.as_dict()["context"]
    assert context["op"] == "bad_axis" and context["reason"]


def test_same_size_declared_axis_replaces_and_meta_not_mutated(registry):
    meta = {"axis":np.array([30.,40.]),"other":7}
    registry.register("same_size_axis",1,Params,lambda x,p:(x,meta))
    pipeline = {"steps":[{"op":"same_size_axis","version":1,"params":{}},{"op":"snv","version":1,"params":{}}]}
    result = registry.run([[1.,2.]],pipeline,wavelengths=[1.,2.])
    np.testing.assert_array_equal(result.wavelengths,[30.,40.])
    assert "axis" in meta and result.steps[0]["meta"]["other"] == 7
