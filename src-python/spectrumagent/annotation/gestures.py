"""R40–R44: session references resolved through the existing annotation engines."""
import numpy as np

from spectrumagent.data import DataError
from .draft import conflict
from .engines.diffusion import prompt_superpixels


def _label_id(sessions, cube_id, class_code):
    for identifier, code, *_ in sessions.drafts.labels(cube_id):
        if code == class_code:
            return identifier
    raise DataError("LABEL_NOT_FOUND", "项目中没有该类 code")


def _check(state, expected_revision):
    if state.segments is None:
        raise DataError("SUPERPIXELS_REQUIRED", "请先生成超像素分割")
    if expected_revision is not None and expected_revision != state.revision:
        raise conflict()


def region_from_gesture(sessions, cube_id, gesture_ref, *, op, class_code=None, confidence=None, expected_revision=None):
    with sessions._lock:
        state = sessions._state(cube_id)
        _check(state, expected_revision)
        seed = sessions.resolve_gesture(cube_id, gesture_ref)
        superpixels = prompt_superpixels(state.segments, seed)
        mask = np.isin(state.segments, superpixels)
        label_id = _label_id(sessions, cube_id, class_code) if op == "add" else None
        sessions.edit(cube_id, mask, action="confirm" if op == "add" else op, label_id=label_id,
                      geometry={"superpixels": superpixels}, source="manual", confidence=confidence)
        row = sessions.drafts.get(cube_id)
        return {"revision": row["revision"], "region_id": row["document"]["regions"][-1]["region_id"],
                "op": op, "n_superpixels": len(superpixels), "pixel_count": int(mask.sum()), "document": row["document"]}


def select_candidates(sessions, diffusion, cube_id, *, method, class_code, params, expected_revision=None):
    with diffusion.superpixels.lock, sessions._lock:
        state = sessions._state(cube_id)
        _check(state, expected_revision)
        if method == "SLIC":
            raise DataError("TOOL_NOT_IMPLEMENTED", "SLIC 选候选的产品语义未定义")
        seed = sessions.resolve_gesture(cube_id, params.gesture_ref)
        label_id = _label_id(sessions, cube_id, class_code)
        result = diffusion.generate(cube_id, seed, threshold=params.threshold, queue_min_similarity=params.queue_min_similarity)
        candidate = result["candidate"]
        mask = np.isin(state.segments, candidate["superpixels"])
        below = result["enqueued"] is False
        sessions.edit(cube_id, mask, action="confirm", label_id=label_id, geometry={"superpixels": candidate["superpixels"]},
                      source="algorithm", confidence="low" if below else "medium")
        row = sessions.drafts.get(cube_id)
        floor = result["params"]["queue_min_similarity"]
        return {"revision": row["revision"], "region_id": row["document"]["regions"][-1]["region_id"],
                "n_superpixels": len(candidate["superpixels"]), "pixel_count": int(mask.sum()),
                "min_similarity": candidate["min_similarity"], "avg_similarity": candidate["avg_similarity"],
                "queue_min_similarity": floor, "below_queue_floor": below,
                "queue_note": f"低于入队下限 {floor:g}，已按人工意图写入，置信度标记 low" if below else None}
