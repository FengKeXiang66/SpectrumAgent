"""Draft service bindings; geometries never enter tool results."""
from contextlib import nullcontext
from spectrumagent.data import DataError
from spectrumagent.annotation.gestures import region_from_gesture, select_candidates as generate_candidates


def add_region(sessions, arguments):
    result = region_from_gesture(sessions, arguments.cube_id, arguments.geometry.gesture_ref,
        op=arguments.op, class_code=getattr(arguments, "class_code", None),
        confidence=getattr(arguments, "confidence", None), expected_revision=arguments.revision)
    summary = {"cube_id": arguments.cube_id, **{key: result[key] for key in (
        "revision", "region_id", "op", "n_superpixels", "pixel_count")}}
    if arguments.op == "add":
        summary["class_code"] = arguments.class_code
    return summary


def select_candidates(sessions, diffusion, arguments):
    if arguments.method == "SLIC":
        raise DataError("TOOL_NOT_IMPLEMENTED", "SLIC 选候选的产品语义未定义")
    if diffusion is None:
        raise DataError("TOOL_NOT_IMPLEMENTED", "扩散服务尚未就绪")
    result = generate_candidates(sessions, diffusion, arguments.cube_id, method=arguments.method,
                                class_code=arguments.class_code, params=arguments.params)
    return {"cube_id": arguments.cube_id, "method": arguments.method, "class_code": arguments.class_code,
            **{key: result[key] for key in ("revision", "region_id", "n_superpixels", "pixel_count", "min_similarity",
                                          "queue_min_similarity", "below_queue_floor", "queue_note")}}


def draft_get(sessions, arguments):
    lease = sessions.resources.lease(arguments.cube_id,required=False,restore=False) if sessions.resources else nullcontext()
    with lease, sessions._lock:
        sessions._state(arguments.cube_id)
        view = sessions.drafts.view(arguments.cube_id)
    document = view["document"]
    return {"cube_id": view["cube_id"], "revision": view["revision"],
            "n_regions": len(document["regions"]) if document else 0,
            "n_classes": len(document["classes"]) if document else 0,
            "updated_at": view["updated_at"], "estimated_mat_bytes": view["estimated_mat_bytes"]}
