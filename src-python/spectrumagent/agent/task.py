"""Pure, versioned task outcome rules; runtime memory is not projected in L0."""
from .workflow import RECOVERABLE


TASK_RESULTS = ("working", "needs_input", "needs_review", "succeeded", "failed", "cancelled")
TASK_SCHEMA_VERSION = 1
CONTEXT_KEYS = frozenset({
    "accepted_candidate_ref", "annotation_version_id", "authorization_cube_id", "auto_execute",
    "candidate_ref", "class_codes", "dataset_catalog", "display_name", "gesture_ref",
    "include_background", "intent", "last_error", "last_run_id", "next_action", "recipe_version_id",
    "rejected_candidate_ref", "revision", "save_denied", "save_requested", "selected_cube_id",
    "stage", "use_defaults", "catalogs", "pending_clarify",
    "requested_stages", "stages_done",
    "cancelled",  # reserved: written by L2 cancellation
})


def normalize_context(context):
    """Return a fresh whitelist projection, including its schema version."""
    result = {key: value for key, value in context.items() if key in CONTEXT_KEYS} if isinstance(context, dict) else {}
    return {**result, "task_schema_version": TASK_SCHEMA_VERSION}


def evaluate_task(state, artifacts):
    """Classify observed business state without reading or changing anything."""
    if state.get("cancelled"):
        return "cancelled"
    error = state.get("last_error")
    if error and error not in RECOVERABLE:
        return "failed"
    if (state.get("next_action") in {"need_seed", "need_annotation", "need_version"}
            or artifacts.get("last_status") in {"need_seed", "need_annotation", "need_version"}
            or error in {"GESTURE_NOT_FOUND", "GESTURE_EXPIRED", "GESTURE_NOT_CURRENT",
                         "LABEL_NOT_FOUND", "ANNOTATION_VERSION_REQUIRED"}):
        return "needs_input"
    if ((state.get("candidate_ref") and state.get("accepted_candidate_ref") != state["candidate_ref"])
            or (state.get("stage") == "annotation" and not state.get("annotation_version_id"))):
        return "needs_review"
    if state.get("annotation_version_id") and (not state.get("last_run_id") or artifacts.get("run_status") == "succeeded"):
        requested = set(state.get("requested_stages") or ())
        if requested and not requested <= set(state.get("stages_done") or ()):
            return "working"
        return "succeeded"
    return "working"
