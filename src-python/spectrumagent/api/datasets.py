import base64
from collections import OrderedDict
import logging
import math
import struct
from typing import Literal
from threading import RLock
from time import perf_counter
from uuid import UUID
import zlib

from fastapi import APIRouter, Query
import numpy as np

from spectrumagent.data import DataError
from spectrumagent.display.falsecolor import FEATURECOLOR_ALGO_VERSION, compose_rgb, map_values, select_feature_bands
from .registry import DatasetRegistry
from .schemas import BandResponse, DatasetRecord, ImportRequest, ImportResponse, PreviewResponse, RegionRequest, RegionResponse

MAX_PREVIEW_SIDE = 512
MAX_JSON_VALUES = 65536


class ColorPreview(PreviewResponse):
    bands: tuple[int, int, int]
    wavelengths: list[float]
    fallback: bool


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
    png_cache = OrderedDict()
    feature_cache = {}
    display_lock = RLock()

    @router.post("/import", response_model=ImportResponse)
    def import_dataset(request: ImportRequest):
        return registry.import_path(request.path, raw=request.raw, data_path=request.data_path)

    @router.get("/{identifier}", response_model=DatasetRecord)
    def info(identifier: UUID):
        ds, _ = registry.get(identifier)
        return DatasetRecord(id=identifier, dataset=ds, existing=True)

    @router.get("/{identifier}/preview", response_model=PreviewResponse | ColorPreview)
    def preview(identifier: UUID, band: int | None = Query(None, ge=0), size: Literal["preview", "full"] = "preview",
                stretch: Literal["auto", "none"] = "auto", bands: str | None = None):
        if (band is None) == (bands is None):
            raise DataError("INVALID_REQUEST", "band 与 bands 必须且只能指定一个")
        try:
            ds, _ = registry.readable(identifier, raw=False)
        except DataError as error:
            if error.code == "SOURCE_CHANGED":
                with display_lock:
                    for key in list(png_cache):
                        if key[0] == str(identifier):
                            del png_cache[key]
                    feature_cache.pop((str(identifier), FEATURECOLOR_ALGO_VERSION), None)
            raise
        stride = 1 if size == "full" else max(1, math.ceil(max(ds.shape[:2]) / MAX_PREVIEW_SIDE))
        if bands is not None:
            fallback = False
            if bands == 'auto':
                feature_key = (str(identifier), FEATURECOLOR_ALGO_VERSION)
                with display_lock:
                    if feature_key not in feature_cache:
                        started = perf_counter()
                        feature_cache[feature_key] = select_feature_bands(ds, ds.shape, ds.wavelengths)
                        logging.getLogger(__name__).debug('display_feature_cache_miss duration_ms=%.3f', (perf_counter()-started)*1000)
                    *rgb_values, fallback = feature_cache[feature_key]
                    rgb = tuple(rgb_values)
            else:
                try:
                    rgb = tuple(int(value) for value in bands.split(','))
                except ValueError as error:
                    raise DataError("INVALID_BANDS", "bands 必须是三个不同波段索引") from error
            if len(rgb) != 3 or len(set(rgb)) != 3 or any(b < 0 or b >= ds.shape[2] for b in rgb):
                raise DataError("INVALID_BANDS", "bands 必须是范围内三个不同波段，顺序对应R/G/B")
            key = (str(identifier), rgb, stretch, size)
            with display_lock:
                if key in png_cache:
                    png_cache.move_to_end(key)
                    return png_cache[key].model_copy(update={'fallback': fallback})
                started = perf_counter()
                image = ds.read_subimage(list(range(0, ds.shape[0], stride)), list(range(0, ds.shape[1], stride)), list(rgb))
                result = ColorPreview(id=identifier, band=rgb[0], bands=rgb,
                    wavelengths=[ds.wavelengths[b] for b in rgb] if ds.wavelengths else [], fallback=fallback,
                    width=image.shape[1], height=image.shape[0], png_base64=compose_rgb(*np.moveaxis(image, 2, 0), stretch))
                png_cache[key] = result
                if len(png_cache) > 8:
                    png_cache.popitem(last=False)
                logging.getLogger(__name__).debug("display_rgb_cache_miss duration_ms=%.3f", (perf_counter()-started)*1000)
                return result
        image = ds.read_subimage(list(range(0, ds.shape[0], stride)), list(range(0, ds.shape[1], stride)), [band])[:, :, 0]
        gray = map_values(image, stretch)
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
