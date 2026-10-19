from pathlib import Path
import sys

import numpy as np
import pytest

from spectrumagent.data import DataError
from spectrumagent.data.readers import EnviReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from cubes import cube


@pytest.mark.parametrize("interleave", ["bsq", "bil", "bip"])
@pytest.mark.parametrize("dtype", ["u1", "<i2", "<i4", "<f4", "<f8", "<u2", ">u2", "<u4", "<i8", "<u8"])
def test_standard_layout_endian_dtype(tmp_path, interleave, dtype):
    hdr, data, logical = cube(tmp_path, interleave=interleave, dtype=dtype, offset=13)
    scaled = EnviReader().open(hdr)
    raw = EnviReader().open(hdr, raw=True)
    assert scaled.shape == (2, 3, 4) and scaled.wavelengths == [1, 2, 3, 4]
    assert scaled.fwhm == [0.1, 0.2, 0.3, 0.4]
    assert isinstance(raw.to_numpy(), np.memmap) and not raw.to_numpy().flags.writeable
    np.testing.assert_array_equal(raw.to_numpy(), logical)
    np.testing.assert_array_equal(scaled.read_region(0, 2, 0, 3), logical.astype(np.float64) / 65535)
    np.testing.assert_array_equal(scaled.read_bands([2, 0]), logical[:, :, [2, 0]].astype(np.float64) / 65535)
    assert scaled.read_pixel(1, 2).dtype == np.float64
    assert raw.metadata["scale_applied"] is False


@pytest.mark.parametrize("extension", [".raw", ".bin", ".dat", ".img"])
def test_sibling_and_explicit_data(tmp_path, extension):
    hdr, data, _ = cube(tmp_path, extension=extension)
    assert EnviReader().open(hdr).data_path == str(data.resolve())
    other = data.with_name("different.bin")
    data.rename(other)
    assert EnviReader().open(hdr, other).data_path == str(other.resolve())


@pytest.mark.parametrize("delta", [-1, 1])
def test_exact_size_gate_precedes_spectral(tmp_path, monkeypatch, delta):
    hdr, data, _ = cube(tmp_path)
    with data.open("r+b") as stream:
        stream.truncate(data.stat().st_size + delta)
    monkeypatch.setattr("spectral.open_image", lambda *_: pytest.fail("spectral called before size gate"))
    monkeypatch.setattr("spectral.io.envi.open", lambda *_a, **_k: pytest.fail("ENVI called before size gate"))
    with pytest.raises(DataError) as caught:
        EnviReader().open(hdr)
    assert caught.value.code == "SIZE_MISMATCH"


def test_invalid_headers_and_missing_files(tmp_path):
    with pytest.raises(DataError) as e:
        EnviReader().open(tmp_path / "absent.hdr")
    assert e.value.code == "FILE_NOT_FOUND"
    hdr, data, _ = cube(tmp_path)
    hdr.write_text("ENVI\nsamples={broken", "utf-8")
    with pytest.raises(DataError) as e:
        EnviReader().open(hdr)
    assert e.value.code == "HEADER_INVALID"


def test_metadata_does_not_materialize_cube(tmp_path, monkeypatch):
    hdr, _, _ = cube(tmp_path)
    monkeypatch.setattr("spectral.io.spyfile.SpyFile.load", lambda *_a, **_k: pytest.fail("implicit full read"))
    dataset = EnviReader().open(hdr)
    assert dataset.shape == (2, 3, 4)
    with pytest.raises(DataError, match="缩放模式"):
        dataset.to_numpy()
