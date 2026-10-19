import base64
import math
import struct
from uuid import UUID
import zlib

from fastapi import APIRouter, Query
import numpy as np

from spectrumagent.data import DataError
from .registry import DatasetRegistry
from .schemas import BandResponse, DatasetRecord, ImportRequest, ImportResponse, PreviewResponse, RegionRequest, RegionResponse

MAX_PREVIEW_SIDE = 512
MAX_JSON_VALUES = 65536


def png_gray(array: np.ndarray) -> str:
    height, width = array.shape
    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    rows = b"".join(b"\x00" + row.tobytes() for row in array)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")


def region_bounds(ds, region):
    if not 0 <= region.l0 < region.l1 <= ds.shape[0] or not 0 <= region.s0 < region.s1 <= ds.shape[1]:
        raise DataError("INVALID_INDEX", "读取区域必须为数据范围内的左闭右开边界")
    return range(region.l0, region.l1), range(region.s0, region.s1)


def json_values(array):
    if np.iscomplexobj(array) or not np.isfinite(array).all():
        raise DataError("NON_JSON_VALUES", "JSON数组只支持有限实数；数据未静默转换")
    return array.tolist()


def make_router(registry: DatasetRegistry):
    router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])

    @router.post("/import", response_model=ImportResponse)
    def import_dataset(request: ImportRequest):
        return registry.import_path(request.path, raw=request.raw, data_path=request.data_path)

    @router.get("/{identifier}", response_model=DatasetRecord)
    def info(identifier: UUID):
        ds, _ = registry.get(identifier)
        return DatasetRecord(id=identifier, dataset=ds, existing=True)

    @router.get("/{identifier}/preview", response_model=PreviewResponse)
    def preview(identifier: UUID, band: int = Query(0, ge=0)):
        ds, _ = registry.readable(identifier, raw=False)
        stride = max(1, math.ceil(max(ds.shape[:2]) / MAX_PREVIEW_SIDE))
        image = ds.read_subimage(list(range(0, ds.shape[0], stride)), list(range(0, ds.shape[1], stride)), [band])[:, :, 0]
        if not np.isfinite(image).all():
            raise DataError("NON_JSON_VALUES", "预览包含非有限值，请检查源数据")
        low, high = image.min(), image.max()
        gray = np.zeros_like(image, dtype=np.uint8) if high == low else np.clip((image-low) / (high-low) * 255, 0, 255).astype(np.uint8)
        return PreviewResponse(id=identifier, band=band, width=gray.shape[1], height=gray.shape[0], png_base64=png_gray(gray))

    @router.post("/{identifier}/band/{i}", response_model=BandResponse)
    def band(identifier: UUID, i: int, region: RegionRequest):
        ds, raw = registry.readable(identifier, region.raw)
        rows, cols = region_bounds(ds, region)
        if len(rows) * len(cols) > MAX_JSON_VALUES:
            raise DataError("REGION_TOO_LARGE", "JSON波段区域超过65536个数值；请缩小区域")
        values = ds.read_subimage(list(rows), list(cols), [i])[:, :, 0]
        return BandResponse(id=identifier, band=i, shape=values.shape, raw=raw, values=json_values(values))

    @router.post("/{identifier}/region", response_model=RegionResponse)
    def region(identifier: UUID, region: RegionRequest):
        ds, raw = registry.readable(identifier, region.raw)
        rows, cols = region_bounds(ds, region)
        if len(rows) * len(cols) * ds.shape[2] > MAX_JSON_VALUES:
            raise DataError("REGION_TOO_LARGE", "JSON立方体区域超过65536个数值；请缩小区域")
        values = ds.read_region(region.l0, region.l1, region.s0, region.s1)
        return RegionResponse(id=identifier, shape=values.shape, raw=raw, values=json_values(values))

    return router
