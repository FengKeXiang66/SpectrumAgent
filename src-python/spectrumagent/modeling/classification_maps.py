"""Bounded categorical evaluation tiles and position-aware pixel drill-down."""
import base64
import numpy as np
from . import ModelingError
from .evaluation import summarize
from .inference import png_rgb


def observations(store, identifier):
    result = store.artifact(identifier, "observations", fields=["y", "groups", "cube_index", "flat_index", "fold_index", "raw_pred", "confidence"])
    if "raw_pred" not in result:
        probability = store.artifact(identifier, "observations", fields=["probabilities"])["probabilities"]
        result.update(raw_pred=probability.argmax(axis=1), confidence=probability.max(axis=1))
    return result


def tile(store, identifier, *, cube_index=0, layer="prediction", level=0, tile_x=0, tile_y=0,
         size=256, hidden=None, colors=None):
    ev = store.get(identifier)
    if not 0 <= cube_index < len(ev["cubes"]) or layer not in ("prediction", "truth", "errors", "rejected", "confidence", "base"):
        raise ModelingError("INVALID_MAP_REQUEST", "分类图参数非法")
    if not 0 <= level <= 20 or min(tile_x, tile_y) < 0 or not 1 <= size <= 256:
        raise ModelingError("INVALID_MAP_REQUEST", "瓦片尺寸或层级非法")
    cube = ev["cubes"][cube_index]
    height, width = cube["shape"][:2]
    scale = 2**level
    x0, y0 = tile_x*size*scale, tile_y*size*scale
    if x0 >= width or y0 >= height:
        raise ModelingError("TILE_OUT_OF_BOUNDS", "瓦片超出图像")
    w, h = min(size, (width-x0+scale-1)//scale), min(size, (height-y0+scale-1)//scale)
    rgb = np.full((h, w, 3), [35, 45, 54], dtype=np.uint8)
    if layer == "base":
        from pathlib import Path
        dataset, _ = store.registry.readable(cube["cube_id"], raw=False)
        for key, path in (("header", dataset.header_path), ("data", dataset.data_path)):
            try:
                store.verify(Path(path), cube["source_hashes"][key])
            except ModelingError:
                raise ModelingError("SOURCE_CHANGED", "底图源身份与评价快照不一致") from None
        gray = dataset.read_subimage(list(range(y0, min(height, y0+h*scale), scale)),
                                    list(range(x0, min(width, x0+w*scale), scale)), [cube["shape"][2]//2])[:, :, 0]
        gray = np.clip(np.nan_to_num(gray)*255, 0, 255).astype(np.uint8)
        rgb = np.repeat(gray[:, :, None], 3, axis=2)
    obs = observations(store, identifier)
    mask = obs["cube_index"] == cube_index
    truth, positions = obs["y"][mask], obs["flat_index"][mask]
    confidence, predicted = obs["confidence"][mask], obs["raw_pred"][mask].copy()
    predicted[confidence < ev["threshold"]] = -2
    rr, cc = positions//width, positions % width
    inside = (rr >= y0) & (rr < y0+h*scale) & (cc >= x0) & (cc < x0+w*scale)
    cells = ((rr[inside]-y0)//scale*w+(cc[inside]-x0)//scale).astype(np.int64)
    counts = np.bincount(cells, minlength=h*w)
    active = counts > 0
    flat_rgb = rgb.reshape(-1, 3)
    if layer == "confidence":
        means = np.divide(np.bincount(cells, weights=confidence[inside], minlength=h*w), counts,
                          out=np.zeros(h*w), where=active)
        values = (means[active]*255).astype(np.uint8)
        flat_rgb[active] = np.column_stack([255-values, values, np.full(len(values), 120)])
    elif layer in ("errors", "rejected"):
        marked = (predicted < 0) if layer == "rejected" else ((predicted >= 0) & (predicted != truth))
        hits = np.bincount(cells, weights=marked[inside], minlength=h*w) > 0
        flat_rgb[active] = [75, 95, 95]
        flat_rgb[hits] = [220, 170, 40] if layer == "rejected" else [184, 50, 39]
    elif layer != "base" and len(cells):
        values = truth[inside] if layer == "truth" else predicted[inside]
        radix = len(ev["classes"])+3
        keys, frequencies = np.unique(cells*radix+values+3, return_counts=True)
        occupied, classes = keys//radix, keys % radix-3
        order = np.lexsort((classes, -frequencies, occupied))
        sorted_cells = occupied[order]
        first = np.r_[True, sorted_cells[1:] != sorted_cells[:-1]]
        selected_cells, selected_classes = sorted_cells[first], classes[order][first]
        flat_rgb[selected_cells[selected_classes < 0]] = [220, 170, 40]
        for value in np.unique(selected_classes[selected_classes >= 0]):
            if value in (hidden or []):
                continue
            color = (colors or {}).get(str(value), ev["classes"][value]["color"])
            try:
                flat_rgb[selected_cells[selected_classes == value]] = [int(color[j:j+2], 16) for j in (1, 3, 5)]
            except (ValueError, IndexError):
                raise ModelingError("INVALID_COLOR", "类别颜色须为#RRGGBB") from None
    try:
        stats = store.artifact(identifier, "mapstats-"+str(cube_index))
    except ModelingError as error:
        if error.code != "ARTIFACT_NOT_FOUND":
            raise
        report = summarize(truth, obs["raw_pred"][mask], obs["groups"][mask], confidence,
                           obs["fold_index"][mask], labels=list(range(len(ev["classes"]))), threshold=ev["threshold"])
        stats = report["populations"]["accepted"]["scores"]["pixel"]
        store.cache(identifier, "mapstats-"+str(cube_index), stats)
    return {"evaluation_id": identifier, "cube_index": cube_index, "cube_id": cube["cube_id"], "layer": layer,
            "width": w, "height": h, "original_width": width, "original_height": height,
            "level": level, "tile_x": tile_x, "tile_y": tile_y, "scale_pixels": scale,
            "mime": "image/png", "png_base64": png_rgb(rgb),
            "legend": ev["classes"], "stats": stats,
            "limitation": "仅有真值OOF位置参加评价；深色为未显示/未评价；缩略格分类取多数（同票按冻结索引，拒识优先），误分/拒识任一存在即高亮，得分取均值；底图取中间波段；物理尺度未知，单位px。"}


def pixel(store, identifier, *, cube_index=0, row=0, column=0, true_label=None, predicted_label=None, offset=0, limit=50,
          all_cubes=False, end_row=None, end_column=None):
    ev = store.get(identifier)
    if not 0 <= cube_index < len(ev["cubes"]):
        raise ModelingError("INVALID_MAP_REQUEST", "图像不存在")
    cube = ev["cubes"][cube_index]
    h, w = cube["shape"][:2]
    if not 0 <= row < h or not 0 <= column < w:
        raise ModelingError("PIXEL_OUT_OF_BOUNDS", "像素超出图像")
    obs = observations(store, identifier)
    predicted = obs["raw_pred"].copy()
    predicted[obs["confidence"] < ev["threshold"]] = -2
    selected = np.ones(len(obs["y"]), dtype=bool) if all_cubes else obs["cube_index"] == cube_index
    if true_label is not None:
        selected &= obs["y"] == true_label
    if predicted_label is not None:
        selected &= predicted == predicted_label
    indices = np.flatnonzero(selected)
    matches = np.flatnonzero((obs["cube_index"] == cube_index) & (obs["flat_index"] == row*w+column))
    pack = store.artifact(identifier, "model")
    p = int(matches[0]) if len(matches) else None
    rows = [{"cube_index": int(obs["cube_index"][i]), "cube_id": ev["cubes"][int(obs["cube_index"][i])]["cube_id"],
             "row": int(obs["flat_index"][i]//ev["cubes"][int(obs["cube_index"][i])]["shape"][1]),
             "column": int(obs["flat_index"][i] % ev["cubes"][int(obs["cube_index"][i])]["shape"][1]),
             "true_label": int(obs["y"][i]), "predicted_label": int(predicted[i]),
             "confidence": float(obs["confidence"][i]), "fold_index": int(obs["fold_index"][i])}
            for i in indices[offset:offset+limit]]
    roi = None
    if end_row is not None and end_column is not None:
        if not row < end_row <= h or not column < end_column <= w:
            raise ModelingError("INVALID_REGION", "选区终点须为图内有效左闭右开边界")
        rr, cc = obs["flat_index"]//w, obs["flat_index"] % w
        inside = (obs["cube_index"] == cube_index) & (rr >= row) & (rr < end_row) & (cc >= column) & (cc < end_column)
        n = int(inside.sum())
        sums = np.zeros(pack["calibration"]["input_n_features"])
        squares = sums.copy()
        # Chunk selected spectra to keep large region statistics bounded.
        selected_rows = np.flatnonzero(inside)
        for first in range(0, len(selected_rows), 256):
            block = store.spectra(identifier, selected_rows[first:first+256])
            sums += block.sum(axis=0); squares += np.square(block).sum(axis=0)
        roi = {"count": n, "total_pixels": (end_row-row)*(end_column-column),
               "mean": (sums/n).tolist() if n else None,
               "std": np.sqrt(np.maximum(0, (squares-sums*sums/n)/(n-1))).tolist() if n > 1 else None,
               "limitation": "仅统计选区内参与OOF评价的有效真值像素"}
    processed, feature_axis = None, None
    raw = store.spectra(identifier, slice(p, p+1)) if p is not None else None
    if p is None:
        from pathlib import Path
        dataset, _ = store.registry.readable(cube["cube_id"], raw=False)
        for key, path in (("header", dataset.header_path), ("data", dataset.data_path)):
            store.verify(Path(path), cube["source_hashes"][key])
        candidate = dataset.read_region(row, row+1, column, column+1).reshape(1, -1)
        raw = candidate if np.isfinite(candidate).all() else None
    if p is not None:
        from .inference import apply_with_calibration
        folds = store.artifact(identifier, "fold_models")
        fold = next(f for f in folds if f["fold_index"] == int(obs["fold_index"][p]))
        transformed = apply_with_calibration(fold["calibration"], fold["calibration"]["pipeline"], raw)
        processed = transformed[0, fold["columns"]].tolist()
        feature_axis = [fold["feature_axis"][i] for i in fold["columns"]] if fold["feature_axis"] is not None else None
    return {"evaluation_id": identifier, "cube_id": cube["cube_id"], "row": row, "column": column,
            "status": "evaluated" if p is not None else "not_evaluated", "spectrum": raw[0].tolist() if raw is not None else None,
            "wavelengths": pack["input_wavelengths"], "wavelength_unit": pack["wavelength_unit"],
            "true_label": int(obs["y"][p]) if p is not None else None,
            "predicted_label": int(predicted[p]) if p is not None else None,
            "processed_spectrum": processed, "processed_axis": feature_axis, "region": roi,
            "items": rows, "total": len(indices), "offset": offset, "limit": limit,
            "source": ev["artifacts"]["observations"]}
