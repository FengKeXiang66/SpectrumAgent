"""Project management and request-lifetime identity for all application routes."""
import json
import re

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from backend.database import connect_database
from spectrumagent import projects
from spectrumagent.data import DataError


class Name(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(min_length=1, max_length=100)


class DeleteConfirmation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    confirm_name: str = Field(min_length=1, max_length=100)
    confirmation_token: str = Field(pattern=r'^[0-9a-f]{64}$')


def make_router(database):
    router = APIRouter(prefix='/api/v1/agent/projects', tags=['projects'])
    service = projects.Projects(database)

    @router.get('')
    def listing():
        return service.list()

    @router.post('', status_code=201)
    def create(body: Name):
        return service.create(body.name)

    @router.get('/migration-preview')
    def preview():
        return service.migration_preview()

    @router.put('/{project_id}/current')
    def select(project_id: str):
        return service.select(project_id)

    @router.get('/{project_id}/deletion-preview')
    def deletion_preview(project_id: str):
        return service.deletion_preview(project_id)

    @router.post('/{project_id}/trash')
    def delete(project_id: str, body: DeleteConfirmation, request: Request):
        def busy(_project, session_ids):
            state = request.app.state
            dialogue = getattr(getattr(state, 'agent_tools', None), 'experiment_dialogue', None)
            if dialogue and any(dialogue.tasks.active(sid) or dialogue.study.has_active(sid)
                                or dialogue.inference.service.has_active(sid) for sid in session_ids):
                return True
            tasks = getattr(getattr(state, 'agent_sessions', None), 'annotation_tasks', None)
            if tasks:
                with tasks.lock:
                    return any(t['owner_session_id'] in session_ids and t['task_status'] in {'queued','running'}
                               for t in tasks.receipts.values())
            return False
        return service.delete(project_id, body.confirm_name, body.confirmation_token, is_busy=busy)

    @router.post('/{project_id}/restore')
    def restore(project_id: str):
        return service.restore(project_id)

    return router


UUID = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
PATHS = [(rf'/(?:datasets|annotations)/({UUID})(?:/|$)', 'cube'),
         (rf'/(?:preprocess|workspace)/recipes/({UUID})(?:/|$)', 'recipe'),
         (rf'/preprocess/runs/({UUID})(?:/|$)', 'preprocess'),
         (rf'/models/runs/({UUID})(?:/|$)', 'training'),
         (rf'/models/registry/({UUID})(?:/|$)', 'model'),
         (rf'/models/classification/({UUID})(?:/|$)', 'evaluation'),
         (rf'/labels/({UUID})(?:/|$)', 'label'),
         (rf'/experiments/({UUID})(?:/|$)', 'experiment')]


class ProjectMiddleware:
    """A chat always uses its immutable project, not the desktop's new selection.

    This binds identity only. Domain services and ScopedToolRegistry perform the
    same resource checks when invoked without HTTP. Responses do not reveal the
    existence or owning project of a rejected identifier.
    """
    def __init__(self, app, database, token, boot_id, pid):
        self.app, self.database, self.token = app, database, token
        self.headers = {'X-SpectrumAgent-Boot-Id': boot_id, 'X-SpectrumAgent-Pid': str(pid)}

    async def __call__(self, scope, receive, send):
        import secrets
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        if not secrets.compare_digest(headers.get(b'authorization', b''), ('Bearer '+self.token).encode()):
            return await self.app(scope, receive, send)
        path = scope['path']
        try:
            session = re.search(rf'/agent/sessions/({UUID})(?:/|$)', path)
            with connect_database(self.database) as db:
                identity = projects.current(db)
            if session:
                identity = projects.session_project(self.database, session[1])
            # Management requests must not count themselves as resource jobs.
            management = path.startswith('/api/v1/agent/projects')
            with projects.bind(identity), projects.activity(self.database, identity, enabled=not management):
                if not management:
                    with connect_database(self.database) as db:
                        for pattern, kind in PATHS:
                            match = re.search(pattern, path)
                            # Session /experiments/<task> has session-owned task
                            # IDs; the task service validates those itself.
                            if match and not (session and kind == 'experiment'):
                                projects.require(db, kind, match[1])
                        from urllib.parse import parse_qs
                        query = {k: v[-1] for k, v in parse_qs(scope.get('query_string', b'').decode()).items()}
                        projects.check_document(db, query)
                # Validate structured references before handlers that use raw SQL.
                # Replay the exact bytes; no user body is rewritten or logged.
                if not management and b'application/json' in headers.get(b'content-type', b''):
                    messages = []
                    while True:
                        message = await receive()
                        messages.append(message)
                        if message['type'] != 'http.request' or not message.get('more_body'):
                            break
                    try:
                        body = json.loads(b''.join(m.get('body', b'') for m in messages))
                    except (ValueError, UnicodeError):
                        body = None  # Let FastAPI return its normal validation error.
                    if body is not None:
                        # Session creation explicitly chooses its immutable project.
                        if path == '/api/v1/agent/sessions':
                            with connect_database(self.database) as db:
                                if isinstance(body, dict) and body.get('project_id'):
                                    projects.require_project(db, body['project_id'])
                        else:
                            with connect_database(self.database) as db:
                                projects.check_document(db, body)
                    index = 0
                    async def replay():
                        nonlocal index
                        if index < len(messages):
                            value = messages[index]
                            index += 1
                            return value
                        return await receive()
                    return await self.app(scope, replay, send)
                return await self.app(scope, receive, send)
        except DataError as error:
            response = JSONResponse(error.as_dict(), status_code=getattr(error, 'status_code', 400), headers=self.headers)
            return await response(scope, receive, send)
