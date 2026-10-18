"""Packaging checks only; these are not data-ingestion or task-pool features."""

import json
import multiprocessing
import os
import sys
import tempfile
from pathlib import Path

from backend.paths import AppPaths


def check_geotiff(paths: AppPaths) -> None:
    import numpy as np
    import rasterio
    from rasterio.crs import CRS
    from rasterio.transform import from_origin

    paths.testdata.mkdir(parents=True, exist_ok=True)
    expected_transform = from_origin(500000, 4000000, 30, 30)
    profile = dict(
        driver="GTiff", height=10, width=12, count=3,
        dtype="float32", crs="EPSG:32650", transform=expected_transform,
    )
    values = np.arange(3 * 10 * 12, dtype=np.float32).reshape(3, 10, 12)
    package = Path(rasterio.__file__).parent
    proj_db = package / "proj_data" / "proj.db"
    gdal_schema = package / "gdal_data" / "gdalvrt.xsd"
    if not proj_db.is_file() or not gdal_schema.is_file():
        raise RuntimeError("冻结包缺少 rasterio proj.db 或 gdalvrt.xsd。")
    with tempfile.TemporaryDirectory(prefix="geotiff-check-", dir=paths.testdata) as temporary:
        sample = Path(temporary) / "generated.tif"
        with rasterio.open(sample, "w", **profile) as dataset:
            dataset.write(values)
        with rasterio.open(sample) as dataset:
            assert dataset.crs == CRS.from_epsg(32650), str(dataset.crs)
            assert dataset.shape == (10, 12), dataset.shape
            assert dataset.count == 3, dataset.count
            assert tuple(dataset.transform[:6]) == tuple(expected_transform[:6])
            assert np.array_equal(dataset.read(), values)
            result = {
                "check": "geotiff", "result": "PASS",
                "diagnostic_pid": os.getpid(),
                "engine_module_loaded": "backend.engine" in sys.modules,
                "uvicorn_module_loaded": "uvicorn" in sys.modules,
                "frozen": bool(getattr(sys, "frozen", False)),
                "executable": sys.executable,
                "crs": str(dataset.crs), "shape": list(dataset.shape),
                "width": dataset.width, "height": dataset.height, "count": dataset.count,
                "transform": list(dataset.transform[:6]), "dtype": dataset.dtypes[0],
                "pixel_values_equal": True,
                "GDAL_DATA": os.environ.get("GDAL_DATA"),
                "PROJ_DATA": os.environ.get("PROJ_DATA"),
                "PROJ_LIB": os.environ.get("PROJ_LIB"),
                "proj_db": str(proj_db), "gdalvrt_xsd": str(gdal_schema),
                "rasterio_module": rasterio.__file__, "numpy_module": np.__file__,
                "python_search_paths": sys.path,
                "sample": str(sample),
            }
    result["sample_removed"] = not sample.exists()
    print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)


def _worker_report(queue) -> None:
    queue.put({
        "worker_pid": os.getpid(), "parent_pid": os.getppid(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "worker_engine_module_loaded": "backend.engine" in sys.modules,
        "worker_uvicorn_module_loaded": "uvicorn" in sys.modules,
    })


def check_worker(paths: AppPaths) -> None:
    """Exactly one temporary spawn worker, no process pool or engine dispatch."""
    before = paths.handshake.read_bytes() if paths.handshake.exists() else None
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    worker = context.Process(target=_worker_report, args=(queue,))
    try:
        worker.start()
        result = queue.get(timeout=15)
        worker.join(timeout=15)
        if worker.is_alive() or worker.exitcode != 0:
            raise RuntimeError(f"打包态 worker 未正常退出：{worker.exitcode}")
        after = paths.handshake.read_bytes() if paths.handshake.exists() else None
        assert before == after, "worker 意外改写引擎握手。"
        assert result["worker_pid"] == worker.pid
        assert result["parent_pid"] == os.getpid()
        print(json.dumps({
            "check": "multiprocessing", "result": "PASS", "diagnostic_pid": os.getpid(),
            **result, "worker_exitcode": worker.exitcode,
            "handshake_unchanged": True,
            "engine_module_loaded": "backend.engine" in sys.modules,
            "uvicorn_module_loaded": "uvicorn" in sys.modules,
        }), flush=True)
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=5)
        queue.close()
        queue.join_thread()
        worker.close()
