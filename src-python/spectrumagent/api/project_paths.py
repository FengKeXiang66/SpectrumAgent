"""Persist project paths; activate output roots only during engine startup."""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictStr

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.storage import guard as storage


class ProjectPathRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    source_path: StrictStr
    output_root: StrictStr


class ProjectPathResponse(ProjectPathRequest):
    data_root: str
    output_enabled: bool


def normalize_path(value):
    """String conversion only; do not stat, resolve, open or create this path."""
    if not value.lower().startswith("smb://"):
        return value
    try:
        parsed = urlsplit(value)
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or parsed.query or parsed.fragment):
            raise ValueError
        parts = unquote(parsed.path).strip("/").split("/")
        if "\\" in parsed.hostname or any(not part or part in (".", "..") or "\\" in part for part in parts):
            raise ValueError
        return "\\\\" + parsed.hostname + "\\" + "\\".join(parts)
    except ValueError:
        raise DataError("INVALID_REQUEST", "SMB 路径须包含服务器与共享目录，且不得包含凭据") from None


def validate_output_root(paths, value, source_path=''):
    candidate = Path(value).resolve()
    guard = storage.for_database(paths.database)
    sources = set(guard.sources)
    if source_path:
        sources.add(Path(source_path).resolve())
    if any(candidate.is_relative_to(source) or source.is_relative_to(candidate) for source in sources):
        raise DataError('WRITE_TO_SOURCE_DENIED', '输出根不得与数据源目录重叠')
    return candidate


def install_project_paths(router, paths):
    with connect_database(paths.database) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS project_path_settings (
            project_id TEXT PRIMARY KEY REFERENCES project(id),
            source_path TEXT NOT NULL, output_root TEXT NOT NULL, updated_at TEXT NOT NULL)""")

    def require_project(db, identifier):
        if db.execute("SELECT 1 FROM project WHERE id=?", (identifier,)).fetchone() is None:
            error = DataError("PROJECT_NOT_FOUND", "项目不存在")
            error.status_code = 404
            raise error

    def response(source_path, output_root):
        guard = storage.for_database(paths.database)
        enabled = bool(output_root and guard.ready and guard.output_root_available
                       and guard.output_root == Path(output_root).resolve())
        return ProjectPathResponse(source_path=source_path, output_root=output_root,
                                   data_root=str(paths.root), output_enabled=enabled)

    @router.get("/projects/{project_id}/paths", response_model=ProjectPathResponse)
    def get_project_paths(project_id: UUID):
        with connect_database(paths.database) as db:
            identifier = str(project_id)
            require_project(db, identifier)
            row = db.execute("SELECT source_path,output_root FROM project_path_settings WHERE project_id=?",
                             (identifier,)).fetchone()
        return response(*(row or ("", "")))

    @router.put("/projects/{project_id}/paths", response_model=ProjectPathResponse)
    def put_project_paths(project_id: UUID, request: ProjectPathRequest):
        source_path, output_root = normalize_path(request.source_path), normalize_path(request.output_root)
        with connect_database(paths.database) as db:
            db.execute("BEGIN IMMEDIATE")
            identifier = str(project_id)
            require_project(db, identifier)
            if output_root:
                candidate = validate_output_root(paths, output_root, source_path)
                others = db.execute("SELECT output_root FROM project_path_settings WHERE project_id<>? AND output_root<>''", (identifier,)).fetchall()
                if any(Path(value).resolve() != candidate for (value,) in others):
                    error = DataError('OUTPUT_ROOT_CONFLICT', '多个项目的输出根不一致')
                    error.status_code = 409
                    raise error
            db.execute("""INSERT INTO project_path_settings (project_id,source_path,output_root,updated_at)
                VALUES (?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET
                source_path=excluded.source_path,output_root=excluded.output_root,updated_at=excluded.updated_at""",
                       (identifier, source_path, output_root, datetime.now(timezone.utc).isoformat()))
        return response(source_path, output_root)
