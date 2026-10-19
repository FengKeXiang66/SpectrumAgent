import json
from pathlib import Path
import sys

import numpy as np
import pytest

from spectrumagent.data import DataError
from spectrumagent.data.readers import BinaryReader, EnviReader, FallbackEnviReader, open_envi

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from cubes import cube


def test_missing_interleave_default_bsq(tmp_path, capsys):
    hdr, _, expected = cube(tmp_path, interleave="bsq")
    hdr.write_text(hdr.read_text("utf-8").replace("interleave=bsq\n", ""), "utf-8")
    ds = open_envi(hdr, raw=True)
    assert ds.interleave == "bsq" and ds.metadata["reader"] == "fallback_envi"
    np.testing.assert_array_equal(ds.to_numpy(), expected)
    assert "default_interleave" in capsys.readouterr().out


@pytest.mark.parametrize("wrapped", [True, False])
@pytest.mark.parametrize("dtype", [12, "uint16", "<u2"])
def test_envi5_json_two_positions_same_normalizer(tmp_path, wrapped, dtype):
    hdr, data, expected = cube(tmp_path, extension=".raw")
    values = {"SAMPLES": 3, "lines": 2, "bands": 4, "data type": dtype, "interleave": "BIL", "byte_order": "LITTLE", "header_offset": 0, "WAVE_LENGTHS": [1, 2, 3, 4], "fwhm": [1, 1, 1, 1], "scale_factor": 65535, "data file": data.name}
    values = {"header": values, "coordinate system string": "retained"} if wrapped else dict(values, arbitrary="retained")
    hdr.write_text(json.dumps(values), "utf-8")
    ds = open_envi(hdr)
    assert ds.metadata["reader"] == "fallback_envi" and ds.wavelengths == [1, 2, 3, 4]
    np.testing.assert_array_equal(ds.read_region(0, 2, 0, 3), expected.astype(np.float64) / 65535)
    assert "retained" in ds.metadata.values()


@pytest.mark.parametrize("delta", [-1, 1])
def test_fallback_cannot_bypass_size_gate(tmp_path, delta):
    hdr, data, _ = cube(tmp_path, interleave="bsq")
    hdr.write_text(hdr.read_text("utf-8").replace("interleave=bsq\n", ""), "utf-8")
    with data.open("r+b") as stream:
        stream.truncate(data.stat().st_size + delta)
    with pytest.raises(DataError) as e:
        open_envi(hdr)
    assert e.value.code == "SIZE_MISMATCH" and "primary_error" in e.value.payload.context


@pytest.mark.parametrize("text", ['{"header":[]}', '{"header":{"samples":3},"SAMPLES":4}', 'bad', 'ENVI\nlines=2\n'])
def test_bad_json_or_classic_still_explicit(tmp_path, text):
    hdr = tmp_path / "bad.hdr"
    hdr.write_text(text, "utf-8")
    with pytest.raises(DataError) as e:
        open_envi(hdr)
    assert e.value.code in ("HEADER_INVALID", "ENVI_NOT_STANDARD")


@pytest.mark.parametrize("reader", ["spectral", "binary", "fallback"])
def test_repeated_mapping_cannot_hide_later_oversize(tmp_path, reader):
    hdr, data, _ = cube(tmp_path)
    if reader == "binary":
        hdr = tmp_path / "head.json"
        hdr.write_text(json.dumps({"samples": 3, "lines": 2, "bands": 4, "data_type": 12, "interleave": "bil"}), "utf-8")
        ds = BinaryReader().open(data, hdr, raw=True)
    else:
        ds = (EnviReader() if reader == "spectral" else FallbackEnviReader()).open(hdr, raw=True)
    assert isinstance(ds.to_numpy(), np.memmap)
    with data.open("ab") as stream:
        stream.write(b"x")
    with pytest.raises(DataError) as e:
        ds.to_numpy()
    assert e.value.code == "SIZE_MISMATCH"


def test_complex_never_silently_loses_imaginary_part(tmp_path):
    data = tmp_path / "complex.bin"
    np.array([1+2j], dtype="<c8").tofile(data)
    hdr = tmp_path / "head.json"
    hdr.write_text(json.dumps({"samples": 1, "lines": 1, "bands": 1, "data_type": "complex64"}), "utf-8")
    with pytest.raises(DataError) as e:
        BinaryReader().open(data, hdr).read_band(0)
    assert e.value.code == "UNSUPPORTED_DTYPE"
    assert BinaryReader().open(data, hdr, raw=True).read_pixel(0, 0)[0] == 1+2j
