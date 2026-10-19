r"""Read-only real-sample acceptance, separate from portable unit tests.

Run with E:\AI_Agent\.venv\Scripts\python.exe scripts/verify_plastic_dataset.py
Optional --root chooses another read-only acquisition root. No source writes.
"""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src-python"))
from spectrumagent.data.readers import EnviReader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("E:/高光谱数据集/plastic"))
    args = parser.parse_args()
    paths = sorted(p for folder in ("pe", "pet", "pp") for p in (args.root / folder).rglob("*.hdr"))
    if len(paths) != 11:
        raise RuntimeError(f"Expected11 headers; found{len(paths)}")
    failures = 0
    for header in paths:
        try:
            start = perf_counter()
            scaled = EnviReader().open(header)
            opened_ms = (perf_counter() - start) * 1000
            raw = EnviReader().open(header, raw=True)
            data = Path(raw.data_path)
            stat = data.stat()
            assert raw.shape == (231, 640, 200) and raw.dtype == "uint16" and raw.interleave == "bil"
            assert stat.st_size == 59136000 and raw.metadata["byte_order"] == 0 and raw.metadata["header_offset"] == 0
            assert len(raw.wavelengths) == 200 and abs(raw.wavelengths[0] - 881.85) < .01 and abs(raw.wavelengths[-1] - 1714.13) < .01
            assert raw.metadata["scale_factor"] == 65535 and raw.metadata["scale_applied"] is False
            direct = np.memmap(data, dtype="<u2", mode="r", shape=(231, 200, 640)).transpose(0, 2, 1)
            mapped = raw.to_numpy()
            assert isinstance(mapped, np.memmap) and not mapped.flags.writeable
            max_band_ms = 0.0
            # Compare every value, one bounded band at a time; never materialize the cube.
            for i in range(200):
                start = perf_counter()
                band = scaled.read_band(i)
                max_band_ms = max(max_band_ms, (perf_counter() - start) * 1000)
                assert band.dtype == np.float64
                np.testing.assert_array_equal(band, direct[:, :, i].astype(np.float64) / 65535)
                np.testing.assert_array_equal(mapped[:, :, i], direct[:, :, i])
            np.testing.assert_array_equal(scaled.read_pixel(11, 29), direct[11, 29].astype(np.float64) / 65535)
            np.testing.assert_array_equal(scaled.read_region(2, 5, 7, 12), direct[2:5, 7:12].astype(np.float64) / 65535)
            assert data.stat().st_mtime_ns == stat.st_mtime_ns and data.stat().st_size == stat.st_size
            assert opened_ms <= 500 and max_band_ms <= 100
            print(json.dumps({"file": str(header), "status": "PASS", "shape": list(raw.shape), "dtype": raw.dtype, "interleave": raw.interleave, "wavelength_nm": [raw.wavelengths[0], raw.wavelengths[-1]], "scale_factor": 65535, "bytes": stat.st_size, "raw_all_values_equal": True, "scaled_all_bands_equal": True, "open_ms": round(opened_ms, 3), "max_read_band_ms": round(max_band_ms, 3)}, ensure_ascii=False), flush=True)
        except Exception as exc:
            failures += 1
            print(json.dumps({"file": str(header), "status": "FAIL", "error": str(exc)}, ensure_ascii=False), flush=True)
    print(json.dumps({"samples": len(paths), "passed": len(paths) - failures, "failed": failures}, ensure_ascii=False))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
