"""R14: one read-only draft binding; geometries never enter tool results."""


def draft_get(sessions, arguments):
    with sessions._lock:
        sessions._state(arguments.cube_id)
        view = sessions.drafts.view(arguments.cube_id)
    document = view["document"]
    return {"cube_id": view["cube_id"], "revision": view["revision"],
            "n_regions": len(document["regions"]) if document else 0,
            "n_classes": len(document["classes"]) if document else 0,
            "updated_at": view["updated_at"], "estimated_mat_bytes": view["estimated_mat_bytes"]}
