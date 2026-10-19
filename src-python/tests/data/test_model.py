from pathlib import Path
import json

import numpy as np
import pytest
from pydantic import ValidationError

from spectrumagent.data import DataError, MemmapAccess, SpectrumDataSet

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def dataset(*, raw=False):
    calls = []
    def factory():
        calls.append("map")
        return np.memmap(FIXTURES / "cube-u16.bin", dtype="uint16", mode="r", shape=(2, 3, 4))
    data = SpectrumDataSet(name="cube", shape=(2, 3, 4), dtype="uint16", interleave="bip", wavelengths=[1, 2, 3, 4], data_path="cube-u16.bin", header_path="cube.json")
    return data.bind(MemmapAccess(factory), raw=raw, scale_factor=65535), calls


def test_scaled_reads_and_full_array_rejection():
    data, calls = dataset()
    assert calls == []  # neither metadata validation nor schema maps/reads data
    with pytest.raises(DataError) as caught:
        data.to_numpy()
    assert caught.value.as_dict()["error"] == "FULL_ARRAY_DISABLED"
    assert calls == []
    expected = np.arange(24).reshape(2, 3, 4) / 65535
    np.testing.assert_array_equal(data.read_band(2), expected[:, :, 2])
    np.testing.assert_array_equal(data.read_region(0, 2, 1, 3), expected[:, 1:3, :])
    np.testing.assert_array_equal(data.read_bands([3, 1]), expected[:, :, [3, 1]])
    np.testing.assert_array_equal(data.read_pixel(1, 2), expected[1, 2])
    assert data.read_band(0).dtype == np.float64
    assert calls == ["map"]


def test_raw_memmap_zero_copy_dn():
    data, _ = dataset(raw=True)
    array = data.to_numpy()
    direct = np.memmap(FIXTURES / "cube-u16.bin", dtype="uint16", mode="r", shape=(2, 3, 4))
    assert isinstance(array, np.memmap) and array.dtype == np.uint16
    assert array.shape == (2, 3, 4) and not array.flags.writeable
    assert data.to_numpy() is array
    np.testing.assert_array_equal(array, direct)
    np.testing.assert_array_equal(data.read_subregion((0, 2), (1, 3)), direct[:, 1:3])


@pytest.mark.parametrize("method,args", [("read_band", (-1,)), ("read_band", (True,)), ("read_pixel", (2, 0)), ("read_region", (0, 3, 0, 1)), ("read_bands", ([],))])
def test_bad_bounds_are_structured(method, args):
    data, calls = dataset()
    with pytest.raises(DataError, match="索引|区域"):
        getattr(data, method)(*args)
    assert calls == []


def test_schema_and_json_do_not_expose_runtime_binding():
    data, calls = dataset()
    schema = SpectrumDataSet.json_schema()
    assert schema == json.loads((Path(__file__).parents[2] / "spectrumagent/data/schema.json").read_text("utf-8"))
    assert set(data.as_dict()) == {"name", "shape", "dtype", "interleave", "wavelengths", "fwhm", "data_path", "header_path", "metadata"}
    assert data.as_dict()["fwhm"] is None and data.as_dict()["shape"] == [2, 3, 4]
    assert schema["additionalProperties"] is False and calls == []
    with pytest.raises(ValidationError):
        SpectrumDataSet(name="bad", shape=(0, 3, 4), dtype="uint16", interleave="bip", wavelengths=[], data_path="a", header_path="b")
