import ctypes
import json
import os
from pathlib import Path
import sys

import numpy as np
import pytest

from spectrumagent.data import DataError
from spectrumagent.data.readers import BinaryReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from cubes import cube


def fields(dtype=12, interleave="bil"):
    return {"samples": 3, "lines": 2, "bands": 4, "data_type": dtype, "interleave": interleave, "wavelengths": [1, 2, 3, 4], "scale_factor": 65535}


def test_json_and_envi_same_values(tmp_path):
    _, data, expected = cube(tmp_path, extension=".bin")
    head = tmp_path / "custom.json"
    head.write_text(json.dumps(fields()), "utf-8")
    ds = BinaryReader().open(data, head)
    np.testing.assert_array_equal(ds.read_region(0, 2, 0, 3), expected.astype(np.float64) / 65535)
    np.testing.assert_array_equal(BinaryReader().open(data, head, raw=True).to_numpy(), expected)


def test_txt_comments_braces_and_normalization(tmp_path):
    _, data, expected = cube(tmp_path, dtype="<f4", interleave="bsq", extension=".bin")
    head = tmp_path / "head.txt"
    head.write_text("# comment\n\nSAMP LES = 3\nlines=2\nbands =4\nDATA_TYPE = float32\n interleave = BSQ\nbyte_order = LITTLE\nwavelength = {1,\n# comment inside\n 2,3,4}\nreflectance scale factor=65535\nunknown = preserved\n", "utf-8")
    ds = BinaryReader().open(data, head)
    np.testing.assert_array_equal(ds.read_region(0, 2, 0, 3), expected.astype(np.float64) / 65535)
    assert ds.metadata["unknown"] == "preserved"


@pytest.mark.parametrize("alias", ["uint16", "<u2", "12"])
def test_alias_and_renamed_data(tmp_path, alias):
    _, data, expected = cube(tmp_path, extension=".bin")
    head = tmp_path / "different.json"
    head.write_text(json.dumps(dict(fields(alias), data_file=data.name)), "utf-8")
    ds = BinaryReader().open(None, head, raw=True)
    np.testing.assert_array_equal(ds.to_numpy(), expected)


@pytest.mark.parametrize("change", [{"samples": None}, {"data_type": None}, {"byte_order": True}, {"header_offset": -1}, {"interleave": "bad"}, {"scale_factor": 0}, {"wavelengths": [1]}, {"fwhm": [1]}, {"lines": 2.5}])
def test_invalid_values(tmp_path, change):
    _, data, _ = cube(tmp_path, extension=".bin")
    head = tmp_path / "head.json"
    head.write_text(json.dumps(dict(fields(), **change)), "utf-8")
    with pytest.raises(DataError) as e:
        BinaryReader().open(data, head)
    assert e.value.code == "HEADER_INVALID"


@pytest.mark.parametrize("missing", ["lines", "samples", "bands", "data_type"])
def test_missing_required(tmp_path, missing):
    head = tmp_path / "head.json"
    values = fields(); del values[missing]
    head.write_text(json.dumps(values), "utf-8")
    with pytest.raises(DataError) as e:
        BinaryReader().open(None, head)
    assert e.value.code == "HEADER_INVALID"


def test_default_bsq_warning_and_size_mismatch(tmp_path, capsys):
    _, data, expected = cube(tmp_path, interleave="bsq", extension=".bin")
    head = tmp_path / "head.json"
    values = fields(); del values["interleave"]
    head.write_text(json.dumps(values), "utf-8")
    np.testing.assert_array_equal(BinaryReader().open(data, head, raw=True).to_numpy(), expected)
    assert "default_interleave" in capsys.readouterr().out
    with data.open("ab") as stream:
        stream.write(b"x")
    with pytest.raises(DataError) as e:
        BinaryReader().open(data, head)
    assert e.value.code == "SIZE_MISMATCH"


def test_explicit_data_overrides_header_key(tmp_path):
    _, data, _ = cube(tmp_path, extension=".bin")
    head = tmp_path / "head.json"
    head.write_text(json.dumps(dict(fields(), data_file="nonexistent.bin")), "utf-8")
    assert BinaryReader().open(data, head).data_path == str(data.resolve())
    with pytest.raises(DataError) as e:
        BinaryReader().open(None, head)
    assert e.value.code == "FILE_NOT_FOUND"


@pytest.mark.parametrize("text", ['{"samples":3,"samples":4}', '{"samples":NaN}', '[]', 'data_type = 12\nwavelength = {1,2'])
def test_corruption_never_silent(tmp_path, text):
    head = tmp_path / "broken.txt"
    head.write_text(text, "utf-8")
    with pytest.raises(DataError):
        BinaryReader().open(None, head)


def test_over_2gb_is_lazy_memmap(tmp_path, monkeypatch):
    data = tmp_path / "large.bin"
    shape = (65537, 16384, 1)
    with data.open("w+b") as stream:
        if os.name == "nt":
            import msvcrt
            from ctypes import wintypes
            api = ctypes.WinDLL("kernel32", use_last_error=True).DeviceIoControl
            api.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
            api.restype = wintypes.BOOL
            returned = wintypes.DWORD()
            assert api(msvcrt.get_osfhandle(stream.fileno()), 0x900C4, None, 0, None, 0, ctypes.byref(returned), None), "FSCTL_SET_SPARSE failed"
        stream.truncate(int(np.prod(shape)) * 2)
    assert data.stat().st_size > 2**31
    header = tmp_path / "large.json"
    header.write_text(json.dumps({"lines": shape[0], "samples": shape[1], "bands": 1, "data_type": 12, "interleave": "bip"}), "utf-8")
    monkeypatch.setattr(np, "fromfile", lambda *_a, **_k: pytest.fail("full-file read"))
    ds = BinaryReader().open(data, header, raw=True)
    access = ds._access
    assert access._array is None
    mapped = ds.to_numpy()
    assert isinstance(mapped, np.memmap) and mapped.nbytes > 2**31
    assert ds.read_pixel(shape[0]-1, shape[1]-1)[0] == 0
    assert ds.read_region(0, 2, 0, 2).shape == (2, 2, 1)
