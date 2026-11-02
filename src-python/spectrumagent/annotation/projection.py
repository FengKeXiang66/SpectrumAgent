"""Read-only, deterministic label-map projection; no DB, files or spectra."""
import json
import math

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage.draw import line
from skimage.measure import find_contours


BACKGROUND = np.ones((3, 3), dtype=bool)  # Dual topology: foreground 4, background 8.


class ProjectionError(ValueError):
    pass


def _box(mask):
    rows, cols = np.nonzero(mask)
    return [int(rows.min()), int(cols.min()), int(rows.max()), int(cols.max())]


def _diagnostic(code, bbox, area, difference, limit, reason):
    return ProjectionError(f"类名={code} bbox={bbox} 面积={area} 对称差={difference} 上限={limit}：{reason}")


def _components(mask, *, structure=None):
    labels, _ = ndimage.label(mask, structure=structure)
    for identifier, slices in enumerate(ndimage.find_objects(labels), 1):
        if slices is not None:
            yield slices, labels[slices] == identifier


def _open_holes(mask):
    """Shortest Euclidean hole/outer-edge pair; one-pixel Bresenham slot."""
    padded = np.pad(mask, 1)
    solid = ndimage.binary_fill_holes(padded, structure=BACKGROUND)
    holes = solid & ~padded
    opened = padded.copy()
    boundary = solid & ~ndimage.binary_erosion(solid)
    distances, nearest = ndimage.distance_transform_edt(~boundary, return_indices=True)
    boxes = []
    for slices, hole in _components(holes, structure=BACKGROUND):
        rows, cols = np.nonzero(hole)
        rows, cols = rows + slices[0].start, cols + slices[1].start
        index = int(np.argmin(distances[rows, cols]))  # Row/column order breaks ties.
        row, col = int(rows[index]), int(cols[index])
        end_row, end_col = nearest[:, row, col]
        rr, cc = line(row, col, int(end_row), int(end_col))
        opened[rr, cc] = False
        boxes.append([int(rows.min()) - 1, int(cols.min()) - 1,
                      int(rows.max()) - 1, int(cols.max()) - 1])
    bridge_pixels = int(np.count_nonzero(padded & ~opened))
    remaining_holes = ndimage.binary_fill_holes(opened, structure=BACKGROUND) & ~opened
    valid = bool(opened.any() and ndimage.label(opened)[1] == 1 and not remaining_holes.any())
    return opened[1:-1, 1:-1], holes[1:-1, 1:-1], boxes, bridge_pixels, valid


def _outline(mask):
    padded = np.pad(mask, 1)
    contours = find_contours(padded, .5, fully_connected="low", positive_orientation="low")
    if len(contours) != 1:
        raise ProjectionError("开槽后轮廓不是单闭合曲线")
    points = []
    for row, col in contours[0]:
        # Each marching-squares point separates exactly one foreground pixel
        # from background. Snap inward, rather than rounding both coordinates.
        low = (math.floor(row), math.floor(col))
        high = (math.ceil(row), math.ceil(col))
        r, c = low if padded[low] else high
        point = [int(c - 1), int(r - 1)]
        if not points or point != points[-1]:
            points.append(point)
    if len(points) > 1 and points[-1] == points[0]:
        points.pop()
    while len(points) < 3:
        points.append(points[-1].copy())
    return points


def _rasterize(points, shape):
    image = Image.new("1", (shape[1], shape[0]))
    ImageDraw.Draw(image).polygon([tuple(point) for point in points], fill=1)
    return np.asarray(image, dtype=bool)


def project(label_map, label_index, mapping, *, rule_version):
    """Return minimal JSON text and metadata; label_index maps indices to codes."""
    if rule_version != 1 or label_map.ndim != 2 or not np.issubdtype(label_map.dtype, np.integer):
        raise ProjectionError("投影规则或 label_map 类型无效")
    shapes = []
    margins = []
    meta = {"shape_count": 0, "class_pixels": {}, "uncertain_pixels": int(np.count_nonzero(label_map == -2)),
            "uncertain_boxes": [], "holes_bridged": 0, "hole_boxes": [], "bridge_pixels": 0,
            "unmapped": [], "simplified": False, "min_margin_px": 0, "projection_rule_version": rule_version}
    for slices, mask in _components(label_map == -2):
        box = _box(mask)
        meta["uncertain_boxes"].append([box[0] + slices[0].start, box[1] + slices[1].start,
                                        box[2] + slices[0].start, box[3] + slices[1].start])
    for identifier in np.unique(label_map[label_map >= 0]):
        code = label_index.get(str(int(identifier)), label_index.get(int(identifier)))
        if not isinstance(code, str):
            raise ProjectionError(f"缺少类下标 {int(identifier)} 的内部 code")
        selected = label_map == identifier
        meta["class_pixels"][code] = int(selected.sum())
        external = mapping.get(code)
        if not isinstance(external, str) or not external:
            meta["unmapped"].append(code)
            continue
        for slices, original in _components(selected):
            row, col = slices[0].start, slices[1].start
            box = [row, col, slices[0].stop - 1, slices[1].stop - 1]
            area = int(original.sum())
            opened, holes, boxes, bridge_pixels, valid = _open_holes(original)
            limit = max(2, math.ceil(.002 * area)) + bridge_pixels
            if not valid:
                raise _diagnostic(code, box, area, bridge_pixels, limit, "孔洞开槽后仍非单连通或区域已消失")
            try:
                local = _outline(opened)
                restored = _rasterize(local, original.shape)
            except (ValueError, IndexError) as error:
                raise _diagnostic(code, box, area, area, limit, str(error)) from error
            difference = int(np.count_nonzero(restored != original))
            if difference > limit or np.any(restored & holes):
                raise _diagnostic(code, box, area, difference, limit, "回栅格超限或污染孔洞")
            # No DP: even the >5000-vertex exception is optional, not a mandate.
            points = [[x + col, y + row] for x, y in local]
            shapes.append(((row, col, area), {"label": external, "points": points,
                           "group_id": None, "shape_type": "polygon", "flags": {}}))
            margins.append(limit - difference)
            meta["holes_bridged"] += len(boxes)
            meta["bridge_pixels"] += bridge_pixels
            meta["hole_boxes"].extend([[r0 + row, c0 + col, r1 + row, c1 + col] for r0, c0, r1, c1 in boxes])
    meta["shape_count"] = len(shapes)
    meta["min_margin_px"] = min(margins, default=0)
    meta["unmapped"].sort()
    payload = {"version": "5.4.1", "flags": {}, "shapes": [shape for _, shape in sorted(shapes, key=lambda item: item[0])]}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), meta
