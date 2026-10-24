"""TASK-07 frozen v1 rasterization, independent of HTTP and session state."""
import numpy as np

from spectrumagent.data import DataError


def polygon_mask(shape, vertices):
    """R19: pixel CENTRES, even-odd, exact on-edge inclusion; no dilation."""
    rows = np.arange(shape[0], dtype=np.float64)[:, None] + .5
    cols = np.arange(shape[1], dtype=np.float64)[None, :] + .5
    inside = np.zeros(shape, dtype=bool)
    on_edge = np.zeros(shape, dtype=bool)
    for (r0, c0), (r1, c1) in zip(vertices, vertices[1:] + vertices[:1]):
        cross = (rows-r0)*(c1-c0) - (cols-c0)*(r1-r0)
        on_edge |= ((cross == 0) & (rows >= min(r0, r1)) & (rows <= max(r0, r1))
                    & (cols >= min(c0, c1)) & (cols <= max(c0, c1)))
        if r0 != r1:
            crossing = ((r0 > rows) != (r1 > rows)) & (cols < c0+(rows-r0)*(c1-c0)/(r1-r0))
            inside ^= crossing
    return inside | on_edge


def encode_rle(mask):
    """Canonical row-major runs, never flatten across a row boundary."""
    runs = []
    for row, pixels in enumerate(mask):
        padded = np.concatenate(([False], pixels, [False])).astype(np.int8)
        changes = np.diff(padded)
        for start, stop in zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)):
            runs.append([row, int(start), int(stop - start)])
    return runs


def decode_rle(runs, shape):
    mask = np.zeros(tuple(shape[:2]), dtype=bool)
    for row, start, length in runs:
        if row < 0 or start < 0 or length <= 0 or row >= mask.shape[0] or start + length > mask.shape[1]:
            raise DataError("TOOL_ARGS_INVALID", "RLE 行游程超出数据集范围")
        mask[row, start:start + length] = True
    return mask


def rasterize_with_conflicts_v1(document, shape):
    """Frozen R6: label_map NEVER derives from owner/conflict."""
    shape = tuple(shape[:2])
    label_map = np.full(shape, -1, dtype=np.int32)
    owner = np.full(shape, -1, dtype=np.int32)
    conflict = np.zeros(shape, dtype=bool)
    for region in document["regions"]:
        geometry = region["geometry"]
        mask = (polygon_mask(shape, geometry["points"]) if geometry["type"] == "polygon"
                else decode_rle(geometry["rows"], shape))
        op = region.get("op", "add")
        if op == "add":
            index = region["class_index"]
            conflict |= mask & (owner >= 0) & (owner != index)
            owner[mask] = index
            label_map[mask] = index
        else:
            owner[mask] = -1
            conflict[mask] = False
            label_map[mask] = -2 if op == "uncertain" else -1
    return label_map, conflict & (label_map >= 0)


def rasterize_v1(document, shape):
    return rasterize_with_conflicts_v1(document, shape)[0]


def rasterize(document, shape):
    if document["raster_rule_version"] != 1:
        raise DataError("TOOL_ARGS_INVALID", "不支持的栅格化规则版本")
    return rasterize_v1(document, shape)
