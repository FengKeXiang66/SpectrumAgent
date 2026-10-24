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


def draft_confirm(sessions, arguments):
    from spectrumagent.data import DataError
    try:
        result = sessions.confirm(arguments.cube_id, revision=arguments.revision,
                                  overwrite=arguments.overwrite or False, note=arguments.note)
    except DataError as error:
        if error.code != "OVERLAP_UNRESOLVED":
            raise
        # Domain refusal is interpretable: only count and prose, never locations.
        return {"overlap_conflicts": error.as_dict()["context"]["conflict_count"],
                "error": error.code, "detail": "存在跨类重叠，请在画布上删区域、改类、擦除或标不确定后重新确认"}
    summary = {key: result[key] for key in ("version_id", "version_no", "training_mat_id", "overlap_conflicts", "n_spectra")}
    if "mat_error" in result:
        # Provider context must not receive exception text containing local paths.
        summary["mat_error"] = "MAT_GENERATION_FAILED"
    return summary
