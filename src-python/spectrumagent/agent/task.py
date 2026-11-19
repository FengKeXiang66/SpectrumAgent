"""Pure, versioned task outcome rules; runtime memory is not projected in L0."""
from .workflow import RECOVERABLE


TASK_RESULTS = ("working", "needs_input", "needs_review", "succeeded", "failed", "cancelled", "modeling_succeeded")
TASK_SCHEMA_VERSION = 1
CONTEXT_KEYS = frozenset({
    'last_preprocess_submission_ref','recipe_editing',
    "accepted_candidate_ref", "annotation_version_id", "authorization_cube_id", "auto_execute",
    "candidate_ref", "class_codes", "dataset_catalog", "display_name", "gesture_ref",
    "include_background", "intent", "last_error", "last_run_id", "next_action", "recipe_version_id",
    "rejected_candidate_ref", "revision", "save_denied", "save_requested", "selected_cube_id",
    "stage", "use_defaults", "catalogs", "pending_clarify", "preprocess_selection",
    "canvas_focus", "label_project_id", "task_selection_source", "task_target",
    "operation_authorization", "annotation_flow_request", "annotation_pending_target",
    "requested_stages", "stages_done",
    "last_modeling_run_id", "last_training_job_id", "modeling_status", "modeling_denied",
    "cancelled",  # reserved: written by L2 cancellation
})


def normalize_context(context):
    """Return a fresh whitelist projection, including its schema version."""
    result = {key: value for key, value in context.items() if key in CONTEXT_KEYS} if isinstance(context, dict) else {}
    if 'last_modeling_run_id' in result:
        from .llm import _egress_blocked
        value = result['last_modeling_run_id']
        if not isinstance(value, str) or len(value) > 128 or _egress_blocked(value) or any(c in value for c in '[]{}'):
            result.pop('last_modeling_run_id')
    if 'last_training_job_id' in result:
        from uuid import UUID
        try:
            if str(UUID(result['last_training_job_id'])) != result['last_training_job_id']: raise ValueError()
        except (ValueError, TypeError, AttributeError):
            result.pop('last_training_job_id')
    if not isinstance(result.get('modeling_status'), str) or result.get('modeling_status') not in {'pending', 'accepted', 'running', 'queued', 'cancelled', 'succeeded', 'failed', 'unknown', 'need_version'}:
        result.pop('modeling_status', None)
    if 'modeling_denied' in result and type(result['modeling_denied']) is not bool:
        result.pop('modeling_denied')
    return {**result, "task_schema_version": TASK_SCHEMA_VERSION}


def evaluate_task(state, artifacts):
    """Classify observed business state without reading or changing anything."""
    if state.get("cancelled"):
        return "cancelled"
    error = state.get("last_error")
    if error in {'TASK_TARGET_REQUIRED', 'OPERATION_NOT_AUTHORIZED', 'LABEL_AMBIGUOUS', 'INVALID_OPERATOR_PARAMS', 'TOOL_ARGS_INVALID',
                 'RECIPE_DRAFT_REVISION_CONFLICT','RECIPE_CONFIRMATION_STALE','RECIPE_DELETED','SOURCE_CHANGED',
                 'QUERY_SNAPSHOT_EXPIRED','QUERY_PAGE_REFERENCE_REQUIRED','QUERY_SCOPE_MISMATCH','PREPROCESS_REFERENCES_REQUIRED','PREPROCESS_RETRY_SCOPE_MISMATCH','RUN_NOT_FOUND'}:
        return 'needs_input'
    if error and error not in RECOVERABLE:
        return "failed"
    batch = artifacts.get('batch_prepare_status')
    if batch == 'accepted':
        return 'working'
    if batch in {'ready', 'partial'}:
        return 'needs_review'
    if batch == 'failed':
        return 'failed'
    if batch in {'need_version', 'need_scope', 'blocked'}:
        return 'needs_input'
    requested = set(state.get('requested_stages') or ())
    if 'modeling' in requested and not requested & {'annotation', 'save'}:
        return _modeling_result(state)
    if (state.get("next_action") in {"need_seed", "need_annotation", "need_version"}
            or artifacts.get("last_status") in {"need_seed", "need_annotation", "need_version"}
            or error in {"GESTURE_NOT_FOUND", "GESTURE_EXPIRED", "GESTURE_NOT_CURRENT",
                         "LABEL_NOT_FOUND", "ANNOTATION_VERSION_REQUIRED"}):
        return "needs_input"
    processed=artifacts.get('preprocess_batch') or {}
    if processed.get('failed',0)>0 or processed.get('remaining_failed',0)>0:
        return 'needs_input' if processed.get('succeeded',0)+processed.get('retained_succeeded',0)>0 else 'failed'
    if (requested=={'preprocess'} and 'preprocess' in set(state.get('stages_done') or ())
            and artifacts.get('run_status')=='succeeded'):
        return 'succeeded'
    if ('preprocess' in requested and requested <= {'preprocess','compare'}
            and requested <= set(state.get('stages_done') or ())
            and processed.get('succeeded',0)>0 and processed.get('failed')==0 and processed.get('truncated') is False):
        return 'succeeded'
    if ((state.get("candidate_ref") and state.get("accepted_candidate_ref") != state["candidate_ref"])
            or (state.get("stage") == "annotation" and not state.get("annotation_version_id"))):
        return "needs_review"
    if 'modeling' in requested:
        return _modeling_result(state)
    if state.get("annotation_version_id") and (not state.get("last_run_id") or artifacts.get("run_status") == "succeeded"):
        requested = set(state.get("requested_stages") or ())
        if requested and not requested <= set(state.get("stages_done") or ()):
            return "working"
        return "succeeded"
    return "working"


def _modeling_result(state):
    if state.get('modeling_status') == 'need_version':
        return 'needs_input'
    if state.get('modeling_status') == 'failed':
        return 'failed'
    if (state.get('modeling_status') == 'succeeded' and state.get('last_modeling_run_id')
            and set(state['requested_stages']) <= set(state.get('stages_done') or ())):
        return 'modeling_succeeded'
    return 'working'
