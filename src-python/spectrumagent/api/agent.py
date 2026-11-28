"""R9/R10 Agent HTTP adapters: preflight failures or finite SSE event streams."""
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Request, Query
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import FileResponse, StreamingResponse
from starlette.responses import Response

from spectrumagent.agent.llm import OpenAICompatibleClient, _json
from spectrumagent.agent.state import AgentStore, StateMachine
from spectrumagent.agent.skill import active_skill, ensure_workflow_skill, _write
from backend.database import connect_database
from spectrumagent.storage import guard


class ZipDownload(FileResponse):
    """Stage verified bundles on disk and release the file when the response ends."""

    def __init__(self, write):
        self.staging = guard.temporary_directory(prefix='spectrum-export-')
        path = Path(self.staging.__enter__()) / 'results.zip'
        try:
            with guard.resolve_write(path, kind='EXPERIMENT_EXPORT').open('xb') as output:
                write(output)
            super().__init__(path, media_type='application/octet-stream')
        except BaseException:
            self.staging.__exit__(None, None, None)
            raise

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.staging.__exit__(None, None, None)


class AgentInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


UUIDText = Annotated[str, Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')]


class ExperimentSelection(AgentInput):
    experiment_id: UUIDText


class ExperimentComparison(AgentInput):
    first_id: UUIDText
    second_id: UUIDText


class GlobalScope(AgentInput):
    kind: Literal['global']


class CreateSession(AgentInput):
    # 2026-11-13 simplification: only global sessions exist; dataset work
    # sessions and their preflight/confirmation flow were removed.
    scope: GlobalScope | None = None
    request_id: UUIDText | None = None
    partial_confirmation_token: Annotated[str, Field(min_length=1, max_length=4096)] | None = None


class SessionSelection(AgentInput):
    cube_id: UUIDText | None


class BatchPrepareCheck(AgentInput):
    dataset_version_id: UUIDText | None = None


class AnnotationFlow(AgentInput):
    request_id: UUIDText
    cube_ids: list[UUIDText] = Field(min_length=1)
    mode: Literal['per_image', 'all']


class TaskSubmit(AgentInput):
    request_id: UUIDText
    authorization_id: UUIDText | None = None


class TaskRetry(TaskSubmit):
    mode: Literal['failed', 'remaining'] = 'failed'


class BatchPrepareAssessment(AgentInput):
    schema_version: Literal[1]
    session_id: UUIDText
    dataset_version_id: UUIDText
    binding_source: Literal['explicit', 'session_scope']
    profile: Literal['annotation-default-v1']
    member_count: int = Field(ge=1)
    checked_at: str
    assessment: Literal['blocked', 'within_profile', 'unknown']
    check_code: Literal['MEMBER_COUNT_LIMIT', 'SHAPE_LIMIT', 'BANDS_LIMIT', 'DTYPE_LIMIT',
                        'ITEM_SOURCE_BYTES_LIMIT', 'TOTAL_SOURCE_BYTES_LIMIT', 'TOTAL_PIXELS_LIMIT',
                        'MEMBERS_UNAVAILABLE', 'METADATA_UNAVAILABLE', 'WITHIN_PROFILE']
    constraint: Literal['member_count', 'shape', 'bands', 'dtype', 'item_source_bytes',
                        'total_source_bytes', 'total_pixels', 'members_available', 'metadata', 'static_profile']
    actual: int | float | Annotated[str, Field(max_length=64, pattern=r'^[A-Za-z0-9_.x-]+$')] | None
    limit: int | float | Annotated[str, Field(max_length=64, pattern=r'^[A-Za-z0-9_.x-]+$')] | None
    runtime_memory_checked: Literal[False]
    execution_guaranteed: Literal[False]
    detail: Annotated[str, Field(max_length=512)]


class RequestMessage(AgentInput):
    request_id: UUIDText | None = None


class Workspace(AgentInput):
    cube_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
    gesture_ref: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")] | None = None


class ContentMessage(RequestMessage):
    content: Annotated[str, Field(min_length=1)]
    workspace: Workspace | None = None


class CheckMessage(RequestMessage):
    check_id: Annotated[str, Field(min_length=1)]
    decision: Literal["approve", "reject"]


class PlanApproval(RequestMessage):
    plan_id: Annotated[str, Field(min_length=1)]
    action: Literal["approve"]


class PlanRejection(RequestMessage):
    plan_id: Annotated[str, Field(min_length=1)]
    action: Literal["reject"]
    reason: Annotated[str, Field(min_length=1)]


class PlanChange(RequestMessage):
    plan_id: Annotated[str, Field(min_length=1)]
    action: Literal["skip", "rollback"]
    step_ref: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(min_length=1)]


PlanMessage = Annotated[PlanApproval | PlanRejection | PlanChange, Field(discriminator="action")]


def make_router(database, tools, llm_factory=None, runtime_info=None, *, session_service=None, engine=None, annotations=None, batch=None):
    router = APIRouter(prefix="/api/v1/agent", tags=["agent"])
    store = AgentStore(database)
    if session_service is None:
        # Compatibility for isolated router users: schema initialization is
        # explicit, never in a connection/import/first-message path.
        from spectrumagent.agent.session_migrations import initialize
        from spectrumagent.agent.sessions import SessionService
        initialize(database)
        session_service = SessionService(database, None, 'isolated-router')
    from spectrumagent.agent.scope import ScopedToolRegistry
    from spectrumagent.agent.session_history import SessionHistory
    from spectrumagent.agent.sessions import identifier
    from spectrumagent.agent.state import _failure
    history = SessionHistory(session_service)
    history.startup()
    from spectrumagent.annotation.tasks import AnnotationTasks
    tasks = AnnotationTasks(batch, session_service.boot_id) if batch else None
    if engine is not None:
        engine.preparation_tasks = tasks
    session_service.annotation_tasks = tasks

    def scoped(session_id, request_id=None):
        return ScopedToolRegistry(tools(), session_service, session_id, engine=engine,
                                  annotations=annotations, batch=batch, request_id=request_id, tasks=tasks)

    @router.get('/sessions/{session_id}/preprocessing-editor')
    def preprocessing_editor(session_id: UUIDText, request: Request,
                             kind: Literal['classification', 'recipe'], cube_id: UUIDText | None = None):
        queries(request, {'kind', 'cube_id'})
        session_service.scope(session_id)
        from spectrumagent.agent.preprocessing_editor import editor_view
        return editor_view(tools(), session_id, kind, cube_id)

    @router.get('/sessions/{session_id}/regression-plan')
    def regression_plan(session_id: UUIDText, request: Request):
        queries(request, set())
        binding = session_service.scope(session_id)
        if binding['scope_kind'] != 'global':
            from spectrumagent.data import DataError
            raise DataError('SESSION_SCOPE_MISMATCH', '请进入全局会话配置回归方案')
        return tools().regression_plans.view(session_id)

    @router.get('/sessions/{session_id}/experiments/{task_id}')
    def experiment_task(session_id: UUIDText, task_id: UUIDText):
        session_service.scope(session_id)
        return tools().experiment_dialogue.tasks.view(session_id, task_id)

    @router.post('/sessions/{session_id}/experiments/{task_id}/cancel')
    def cancel_experiment_task(session_id: UUIDText, task_id: UUIDText):
        session_service.scope(session_id)
        return tools().experiment_dialogue.tasks.cancel(session_id, task_id)

    def experiment_results(session_id):
        from spectrumagent.experiments.results import ExperimentResults
        session_service.scope(session_id)
        return ExperimentResults(tools().experiment_dialogue)

    def experiment_archive(session_id):
        if session_service.scope(session_id)['scope_kind'] != 'global':
            raise _failure('SESSION_SCOPE_MISMATCH', '请在全局会话查看历史实验', 409)
        return experiment_results(session_id)

    def inference_service(session_id):
        return experiment_archive(session_id).dialogue.inference.service

    @router.get('/sessions/{session_id}/pairing-view')
    def pairing_view(session_id: UUIDText, preview_id: UUIDText | None = None,
                     section: Literal['pairs', 'unused', 'issues'] = 'pairs',
                     offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=50),
                     search: str = Query(default='', max_length=200),
                     role: Literal['训练', '测试'] | None = None,
                     label: str | None = Query(default=None, max_length=100)):
        report = experiment_archive(session_id).dialogue.pairing_report(session_id)
        if not report or preview_id and report['preview_id'] != preview_id:
            return {'status':'stale' if report else 'empty', 'preview_id':report['preview_id'] if report else None}
        pairs = report['pairs']
        match = search.strip().casefold()
        items = []
        for index, entry in enumerate(report[section]):
            if section == 'pairs':
                if ((role and entry['role'] != role) or (label and label not in entry['labels'])
                        or match and not any(match in str(entry[key]).casefold() for key in ('hdr','annotation','labels'))):
                    continue
                items.append({'index':index, **{key:entry[key] for key in ('role','hdr','annotation','labels','regions')}})
            elif match in entry.casefold():
                items.append({'index':index, 'text':entry})
        return {'status':'ready', 'preview_id':report['preview_id'], 'items':items[offset:offset+limit], 'total':len(items),
                'labels':sorted({name for pair in pairs for name in pair['labels']}),
                'counts':{key:len(report[key]) for key in ('pairs','unused','issues')}}

    @router.get('/sessions/{session_id}/pairing-view/{preview_id}/files/{index}/{kind}')
    def pairing_file(session_id: UUIDText, preview_id: UUIDText, index: int,
                     kind: Literal['hdr', 'annotation']):
        import hashlib
        report = experiment_archive(session_id).dialogue.pairing_report(session_id)
        if not report or report['preview_id'] != preview_id:
            raise _failure('PAIRING_STALE', '该配对预览已替换，请打开最新预览。', 409)
        if not 0 <= index < len(report['pairs']):
            raise _failure('PAIRING_ROW_NOT_FOUND', '这条配对记录已不可用。', 404)
        row = report['pairs'][index]
        path = Path(row[kind])
        if path.suffix.lower() != {'hdr':'.hdr','annotation':'.json'}[kind] or path.resolve() != path:
            raise _failure('PAIRING_FILE_INVALID', '只能预览这条配对记录中的 HDR 或 JSON 文本。', 422)
        limit = 1024 * 1024
        try:
            with path.open('rb') as stream:
                data = stream.read(limit+1)
            if len(data)>limit:
                raise _failure('PAIRING_FILE_TOO_LARGE', '文件超过 1 MiB，请使用本机编辑器查看。', 413)
            if row.get(kind+'_sha256') and hashlib.sha256(data).hexdigest() != row[kind+'_sha256']:
                raise _failure('PAIRING_FILE_CHANGED', '文件自配对后发生变化，请重新预览。', 409)
            try:
                text = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                if kind != 'hdr':
                    raise
                text = data.decode('gb18030')
        except (OSError, UnicodeError):
            raise _failure('PAIRING_FILE_UNREADABLE', '文件无法读取或文本编码不受支持。', 422) from None
        if chr(0) in text:
            raise _failure('PAIRING_FILE_UNREADABLE', '无法预览二进制文件。', 422)
        return {'name':path.name, 'text':text}

    @router.get('/sessions/{session_id}/foreground-probe')
    def foreground_probe(session_id: UUIDText):
        return experiment_archive(session_id).dialogue.inference.probe_result(session_id)

    @router.get('/sessions/{session_id}/studies/{study_id}')
    def study_status(session_id: UUIDText, study_id: UUIDText):
        return experiment_archive(session_id).dialogue.study.status(session_id,study_id)

    @router.get('/sessions/{session_id}/studies/{study_id}/result')
    def study_result(session_id: UUIDText, study_id: UUIDText):
        return experiment_archive(session_id).dialogue.study.result(session_id,study_id)

    @router.post('/sessions/{session_id}/studies/{study_id}/cancel')
    def cancel_study(session_id: UUIDText, study_id: UUIDText):
        return experiment_archive(session_id).dialogue.study.cancel(session_id,study_id)

    @router.get('/sessions/{session_id}/experiment-history/{model_id}/inferences')
    def inference_history(session_id: UUIDText, model_id: UUIDText):
        return {'items': inference_service(session_id).history(model_id)}

    @router.get('/sessions/{session_id}/experiment-history/{model_id}/inferences/{run_id}')
    def inference_task(session_id: UUIDText, model_id: UUIDText, run_id: UUIDText):
        return inference_service(session_id).status(model_id,run_id,session_id)

    @router.post('/sessions/{session_id}/experiment-history/{model_id}/inferences/{run_id}/focus')
    def focus_inference(session_id: UUIDText, model_id: UUIDText, run_id: UUIDText):
        return experiment_archive(session_id).dialogue.inference.focus_run(session_id,model_id,run_id)

    @router.post('/sessions/{session_id}/experiment-history/{model_id}/inferences/{run_id}/cancel')
    def cancel_inference(session_id: UUIDText, model_id: UUIDText, run_id: UUIDText):
        return inference_service(session_id).cancel(session_id,model_id,run_id)

    @router.get('/sessions/{session_id}/experiment-history/{model_id}/inferences/{run_id}/result')
    def inference_result(session_id: UUIDText, model_id: UUIDText, run_id: UUIDText):
        return inference_service(session_id).result(model_id,run_id)

    @router.get('/sessions/{session_id}/experiment-history/{model_id}/inferences/{run_id}/plots/{file_index}')
    def inference_plot(session_id: UUIDText, model_id: UUIDText, run_id: UUIDText, file_index: int, kind: Literal['prediction','input']='prediction'):
        return inference_service(session_id).plot(model_id,run_id,file_index,kind)

    @router.post('/sessions/{session_id}/experiment-history/{model_id}/inferences/{run_id}/report')
    def prepare_inference_report(session_id: UUIDText, model_id: UUIDText, run_id: UUIDText):
        return inference_service(session_id).prepare_report(model_id,run_id)

    @router.get('/sessions/{session_id}/experiment-history/{model_id}/inferences/{run_id}/export', response_class=Response,
                responses={200: {'content': {'application/octet-stream': {'schema': {'type':'string','format':'binary'}}}}})
    def export_inference(session_id: UUIDText, model_id: UUIDText, run_id: UUIDText):
        service = inference_service(session_id)
        return ZipDownload(lambda output: service.export(model_id, run_id, output=output))

    @router.get('/sessions/{session_id}/experiment-history')
    def experiment_history(session_id: UUIDText, request: Request,
                           offset: int = Query(default=0, ge=0), limit: int = Query(default=20, ge=1, le=50)):
        queries(request, {'offset', 'limit'})
        result = experiment_archive(session_id)
        return {**result.service.archive.list(offset=offset, limit=limit),
                'selected_experiment_id': result.dialogue.selected(session_id)}

    @router.post('/sessions/{session_id}/experiment-history/selection')
    def select_experiment(session_id: UUIDText, body: ExperimentSelection):
        return experiment_archive(session_id).dialogue.select(session_id, body.experiment_id)

    @router.post('/sessions/{session_id}/experiment-history/comparison')
    def compare_experiments(session_id: UUIDText, body: ExperimentComparison):
        return experiment_archive(session_id).service.archive.compare(body.first_id, body.second_id)

    @router.get('/sessions/{session_id}/experiment-history/{experiment_id}/result')
    def archived_experiment_result(session_id: UUIDText, experiment_id: UUIDText):
        return experiment_archive(session_id).summary(session_id, experiment_id=experiment_id)

    @router.get('/sessions/{session_id}/experiment-history/{experiment_id}/plots/{name}')
    def archived_experiment_plot(session_id: UUIDText, experiment_id: UUIDText, name: str):
        return experiment_archive(session_id).plot(session_id, None, name, experiment_id=experiment_id)

    @router.get('/sessions/{session_id}/experiment-history/{experiment_id}/export/{kind}', response_class=Response,
                responses={200: {'content': {'application/octet-stream': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def export_archived_experiment(session_id: UUIDText, experiment_id: UUIDText, kind: str):
        results = experiment_archive(session_id)
        if kind == 'bundle':
            return ZipDownload(lambda output: results.export(session_id, None, kind, experiment_id=experiment_id, output=output))
        data = results.export(session_id, None, kind, experiment_id=experiment_id)
        return Response(data, media_type='application/octet-stream')

    @router.get('/sessions/{session_id}/experiments/{task_id}/result')
    def experiment_result(session_id: UUIDText, task_id: UUIDText):
        return experiment_results(session_id).summary(session_id, task_id)

    @router.get('/sessions/{session_id}/experiments/{task_id}/plots/{name}')
    def experiment_plot(session_id: UUIDText, task_id: UUIDText, name: str):
        return experiment_results(session_id).plot(session_id, task_id, name)

    @router.get('/sessions/{session_id}/experiments/{task_id}/export/{kind}', response_class=Response,
                responses={200: {'content': {'application/octet-stream': {'schema': {'type': 'string', 'format': 'binary'}}}}})
    def export_experiment_result(session_id: UUIDText, task_id: UUIDText, kind: str):
        results = experiment_results(session_id)
        if kind == 'bundle':
            return ZipDownload(lambda output: results.export(session_id, task_id, kind, output=output))
        data = results.export(session_id, task_id, kind)
        return Response(data, media_type='application/octet-stream')

    @router.post('/sessions/{session_id}/annotation-flow')
    def start_annotation(session_id: UUIDText, body: AnnotationFlow, request: Request):
        queries(request, set())
        session_service.scope(session_id)
        if tasks is None:
            raise _failure('TOOL_NOT_IMPLEMENTED', '分割服务不可用', 409)
        if store.pending(session_id):
            raise _failure('SESSION_BUSY', '请先处理当前待确认操作', 409)
        _, prior = history.start(session_id, {'content': 'annotation_mode', **body.model_dump()}, body.request_id)
        if prior:
            response = session_service.flow_requests.get((session_id, body.request_id))
            if response:
                return response
            raise _failure('REQUEST_INTERRUPTED', '原模式请求未完成，请核查任务后发起新请求', 409)
        try:
            result = submit_flow(session_id, body)
        except BaseException:
            history.finish(session_id, body.request_id, 'failed', False)
            raise
        history.finish(session_id, body.request_id, 'completed', True)
        return result

    def submit_flow(session_id, body):
        state = store.context(session_id)
        # A structured UI selection is a user action; model tools cannot call
        # this endpoint or supply this evidence in their tool arguments.
        old = state.get('annotation_flow_request')
        from spectrumagent.agent.sessions import digest
        fingerprint = digest({'cube_ids': body.cube_ids, 'mode': body.mode})
        if old and old['request_id'] == body.request_id:
            if old['fingerprint'] != fingerprint:
                raise _failure('IDEMPOTENCY_CONFLICT', '模式请求 ID 已被占用', 409)
            return old['response']
        from spectrumagent.agent.authorization import AnnotationAuthorization
        from spectrumagent.agent.annotation_flow import submit_flow as submit_preparation_flow, flow_reply
        history.append(session_id, 'user', {'content': '选择提前生成全部超像素' if body.mode == 'all' else '选择逐张生成超像素'}, body.request_id, body.request_id+':input')
        authorizer = AnnotationAuthorization(session_service)
        target = authorizer.pending_target(session_id, state)
        if target and target['cube_ids']:
            if body.cube_ids != target['cube_ids']:
                raise _failure('TASK_TARGET_REQUIRED', '生成范围与已确定的标注范围不一致，请先重新指定范围', 409)
        text = '提前批量生成' if body.mode == 'all' else '逐张生成'
        authorizer.capture(session_id, text, None, body.request_id, state,selected_cube_ids=tuple(body.cube_ids))
        grant = session_service.authorization_records[state['operation_authorization']['authorization_id']]
        store.save_context(session_id, state)
        response = submit_preparation_flow(session_service, tasks, session_id, body.request_id,
                                          body.cube_ids, body.mode, state, grant)
        history.append(session_id, 'done', flow_reply(response), body.request_id, body.request_id+':task')
        return response

    @router.get('/sessions/{session_id}/batch-prepare/{task_id}')
    def task_status(session_id: UUIDText, task_id: UUIDText, request: Request):
        queries(request, set())
        session_service.scope(session_id)
        if tasks is None:
            raise _failure('TASK_NOT_FOUND', '任务不存在', 404)
        return tasks.view(session_id, task_id)

    @router.post('/sessions/{session_id}/annotation-flow/{cube_id}/prepare')
    def prepare_flow_member(session_id: UUIDText, cube_id: UUIDText, body: TaskSubmit, request: Request):
        queries(request, set())
        session_service.scope(session_id)
        if tasks is None:
            raise _failure('TOOL_NOT_IMPLEMENTED', '分割服务不可用', 409)
        from spectrumagent.agent.authorization import AnnotationAuthorization
        state = store.context(session_id)
        if body.authorization_id:
            state = {**state, 'operation_authorization': {'authorization_id': body.authorization_id}}
        grant = AnnotationAuthorization(session_service).require(session_id, state,
                                                               'annotations.prepare', {'cube_id': cube_id})
        return tasks.submit(session_id, body.request_id, [cube_id], grant)

    @router.post('/sessions/{session_id}/annotation-flow/{cube_id}/focus')
    def focus_canvas(session_id: UUIDText, cube_id: UUIDText, request: Request):
        queries(request, set())
        session_service.scope(session_id)
        if engine and engine.resources:
            engine.resources.canvas_focus(session_id, cube_id)
        session_service.remember_canvas(session_id, cube_id)
        return {'cube_id': cube_id, 'focused': True}

    @router.post('/sessions/{session_id}/annotation-flow/{cube_id}/blur')
    def blur_canvas(session_id: UUIDText, cube_id: UUIDText, request: Request):
        queries(request, set())
        session_service.scope(session_id)
        if engine and engine.resources:
            engine.resources.canvas_focus(session_id, cube_id, release=True)
        return {'cube_id': cube_id, 'focused': False}

    @router.get('/sessions/{session_id}/batch-prepare/{task_id}/items')
    def task_items(session_id: UUIDText, task_id: UUIDText, request: Request,
                   after: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
                   version: int | None = Query(default=None, ge=1)):
        queries(request, {'after', 'limit', 'version'})
        session_service.scope(session_id)
        if tasks is None:
            raise _failure('TASK_NOT_FOUND', '任务不存在', 404)
        return tasks.view(session_id, task_id, after=after, limit=limit, version=version)

    @router.post('/sessions/{session_id}/batch-prepare/{task_id}/cancel')
    def cancel_task(session_id: UUIDText, task_id: UUIDText, request: Request):
        queries(request, set())
        session_service.scope(session_id)
        if tasks is None:
            raise _failure('TASK_NOT_FOUND', '任务不存在', 404)
        return tasks.cancel(session_id, task_id)

    @router.post('/sessions/{session_id}/batch-prepare/{task_id}/retry')
    def retry_task(session_id: UUIDText, task_id: UUIDText, body: TaskRetry, request: Request):
        queries(request, set())
        session_service.scope(session_id)
        if tasks is None:
            raise _failure('TASK_NOT_FOUND', '任务不存在', 404)
        with tasks.lock:
            parent = tasks._owned(session_id, task_id)
            grant = parent['grant']
        accepted = tasks.retry(session_id, task_id, body.request_id, grant, body.mode)
        history.append(session_id, 'user', {'content': '重试失败项' if body.mode == 'failed' else '继续未完成的超像素任务'}, body.request_id, body.request_id+':input')
        history.append(session_id, 'done', {'content': '超像素任务已受理。', 'step_count': 0,
            'task_result': 'working', 'annotation_task_id': accepted['task_id']}, body.request_id, body.request_id+':task')
        return accepted

    def queries(request, allowed):
        if set(request.query_params) - set(allowed) or any(len(request.query_params.getlist(k))>1 for k in request.query_params):
            raise _failure('INVALID_REQUEST', '不支持的查询参数')
    factory = llm_factory or (lambda session_id: OpenAICompatibleClient(database, session_id=session_id))

    def describe_runtime(registry):
        """Report which orchestration is actually running, not a guessed version."""
        info = dict(runtime_info or {})
        info.setdefault("tool_catalogue_version", getattr(registry, "catalogue_version", 1))
        info.setdefault("tool_count", len(registry.snapshot()))
        return info

    @router.post("/sessions")
    def create_session(body: CreateSession, request: Request):
        queries(request,set())
        registry = tools()
        if getattr(registry, "catalogue_version", 1) == 2:
            try:
                with connect_database(database) as db, _write(db):
                    ensure_workflow_skill(db, registry)
            except Exception as error:
                if getattr(error, "code", None) == "SKILL_NOT_ACTIVE":
                    error.status_code = 409
                raise
        session = session_service.create(body.scope.model_dump() if body.scope else None,
                                         body.request_id, body.partial_confirmation_token)
        with connect_database(database) as db:
            skill = active_skill(db)
        session["skill_name"] = skill["name"]
        session["skill_version_no"] = skill["version_no"]
        session["runtime"] = describe_runtime(registry)
        return session

    @router.post('/sessions/{session_id}/batch-prepare/check', response_model=BatchPrepareAssessment)
    def check_batch_prepare(session_id: UUIDText, body: BatchPrepareCheck, request: Request):
        queries(request, set())
        from spectrumagent.annotation.prepare_admission import check_version
        binding = session_service.scope(session_id)
        version = body.dataset_version_id
        if binding['scope_kind'] == 'dataset_version':
            if version is not None and version != binding['dataset_version_ref']:
                raise _failure('SESSION_SCOPE_MISMATCH', '检查版本与工作会话绑定不一致，请进入全局或对应工作会话', 409)
            version = version or binding['dataset_version_ref']
        if version is None:
            raise _failure('BATCH_VERSION_REQUIRED', '请明确要核对的冻结版本', 422)
        frozen, result = check_version(session_service.versions, session_service.registry, version)
        return {**result, 'schema_version': 1, 'session_id': session_id, 'dataset_version_id': frozen['id'],
                'binding_source': 'explicit' if body.dataset_version_id else 'session_scope',
                'profile': 'annotation-default-v1', 'member_count': len(frozen['members']),
                'runtime_memory_checked': False, 'execution_guaranteed': False}

    @router.get('/sessions')
    def list_sessions(request: Request, kind: Literal['global','dataset_version'] | None = None,
                      dataset_version_id: UUIDText | None = None,
                      limit: int = Query(default=20, ge=1, le=50),
                      cursor: str | None = Query(default=None, max_length=4096)):
        queries(request, {'kind','dataset_version_id','limit','cursor'})
        return session_service.list(kind=kind,dataset_version_id=dataset_version_id,limit=limit,cursor=cursor)

    @router.get('/sessions/{session_id}')
    def get_session(session_id: UUIDText, request: Request):
        queries(request,set())
        result=session_service.detail(session_id)
        result['effective_tool_count']=len(scoped(session_id).snapshot())
        return result

    def experiment_active(session_id):
        dialogue = getattr(tools(), 'experiment_dialogue', None)
        return bool(dialogue and (dialogue.tasks.active(session_id) or dialogue.study.has_active(session_id)
                                  or dialogue.inference.service.has_active(session_id)))

    @router.post('/sessions/{session_id}/archive')
    def archive_session(session_id: UUIDText, request: Request):
        queries(request,set())
        return session_service.archive(session_id, experiment_active=experiment_active)

    @router.get('/sessions/{session_id}/members')
    def list_members(session_id: UUIDText, request: Request, after: int = Query(default=0,ge=0), limit: int = Query(default=50,ge=1,le=100)):
        queries(request,{'after','limit'})
        return {'session_id':session_id,**session_service.members(session_id,after=after,limit=limit)}

    @router.get('/sessions/{session_id}/history')
    def get_history(session_id: UUIDText, request: Request, before: int | None = Query(default=None,ge=0),
                    after: int | None = Query(default=None,ge=0),limit: int = Query(default=50,ge=1,le=100)):
        queries(request,{'before','after','limit'})
        return history.page(session_id,before=before,after=after,limit=limit)

    @router.patch('/sessions/{session_id}/selection')
    def select_cube(session_id: UUIDText, body: SessionSelection, request: Request):
        queries(request,set())
        result=session_service.select(session_id,body.cube_id)
        result['effective_tool_count']=len(scoped(session_id).snapshot())
        return result

    @router.get('/sessions/{session_id}/requests/{request_id}')
    def request_state(session_id: UUIDText, request_id: UUIDText, request: Request):
        queries(request, set())
        return history.request_state(session_id, request_id)

    @router.post('/sessions/{session_id}/requests/{request_id}/cancel')
    def cancel_request(session_id: UUIDText, request_id: UUIDText, request: Request):
        queries(request, set())
        return history.cancel(session_id, request_id)

    @router.post("/sessions/{session_id}/messages", response_class=StreamingResponse,
                 responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}})
    def message(session_id: str, body: ContentMessage | CheckMessage | PlanMessage, request: Request, progress: bool = False):
        queries(request,{'progress'})
        identifier(session_id)
        payload=body.model_dump(exclude_none=True)
        request_id=payload.pop('request_id',None)
        events = history.execute(session_id,payload,
            lambda rid: StateMachine(store, session_id, factory(session_id), scoped(session_id,rid)),request_id)
        async def encode():
            import anyio
            def pull():
                try:return next(events)
                except StopIteration:return None
            try:
                while True:
                    item = await anyio.to_thread.run_sync(pull, abandon_on_cancel=True)
                    if item is None:break
                    event, data = item
                    if event == 'progress' and not progress:continue
                    yield "event: " + event + "\ndata: " + _json(data) + "\n\n"
            finally:
                close = getattr(events, 'close', None)
                if close:close()
        return StreamingResponse(encode(), media_type="text/event-stream")

    @router.get("/runtime")
    def runtime():
        """Observable runtime version of the orchestration actually in use."""
        registry = tools()
        with connect_database(database) as db:
            try:
                skill = active_skill(db)
            except Exception:
                skill = {"name": None, "id": None, "version_no": None}
            sessions = db.execute(
                "SELECT s.id, v.name FROM agent_session s JOIN skill_version v ON v.id=s.skill_version_id"
            ).fetchall()
        by_skill = {}
        for _identifier, name in sessions:
            by_skill[name] = by_skill.get(name, 0) + 1
        info = describe_runtime(registry)
        info.update({
            "skill_name": skill["name"],
            "skill_version_id": skill["id"],
            "skill_version_no": skill["version_no"],
            "sessions_by_skill": by_skill,
            "assistant_transport": {"protocol": 1, "progress": True, "cancel": True, "context": "journal-v1"},
        })
        return info

    @router.get("/sessions/{session_id}/steps")
    def steps(session_id: str):
        columns = ("seq", "tool", "status", "arguments_json", "result_digest", "result_summary", "latency_ms", "created_at")
        return {"session_id": session_id, "steps": [{key: row[key] for key in columns} for row in store.steps(session_id)]}

    return router
