"""Trusted project identity and resource ownership, independent of model context.

HTTP requests and conversation generators bind identity for their lifetime. Worker
threads capture that binding at submission, never the mutable desktop selection.
"""
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from functools import wraps
import json
from uuid import uuid4
from threading import RLock

from backend.database import connect_database
from spectrumagent.data import DataError


_identity = ContextVar('spectrum_project_identity', default=None)
_maintenance = ContextVar('spectrum_project_maintenance', default=False)
_activity_lock = RLock()
_activities = {}
_changing = set()


def project_busy():
    error = DataError('PROJECT_BUSY', '项目仍有操作或任务在执行，请结束后重试')
    error.status_code = 409
    return error


@contextmanager
def activity(database, identifier, *, enabled=True):
    """Keep native requests/SSE alive through their complete response lifetime."""
    if not enabled:
        yield
        return
    key = (str(database), identifier)
    with _activity_lock:
        if key in _changing:
            raise project_busy()
        with connect_database(database) as db:
            require_project(db, identifier)
        _activities[key] = _activities.get(key, 0) + 1
    try:
        yield
    finally:
        with _activity_lock:
            remaining = _activities[key] - 1
            if remaining:
                _activities[key] = remaining
            else:
                _activities.pop(key)


@contextmanager
def project_change(database, identifier):
    key = (str(database), identifier)
    with _activity_lock:
        if key in _changing or _activities.get(key):
            raise project_busy()
        _changing.add(key)
    try:
        yield
    finally:
        with _activity_lock:
            _changing.discard(key)


def denied():
    error = DataError('RESOURCE_NOT_FOUND', '资源不存在或不属于当前项目')
    error.status_code = 404
    return error


def current(db):
    identity = _identity.get()
    if identity is not None:
        return require_project(db, identity)
    # Maintenance/tests before the project migration still use the default.
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='desktop_project'").fetchone():
        row = db.execute('SELECT project_id FROM desktop_project WHERE singleton=1').fetchone()
        if row:
            return row[0]
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='project'").fetchone():
        return None
    row = db.execute("SELECT id FROM project WHERE name='默认项目' ORDER BY created_at,id LIMIT 1").fetchone()
    return row[0] if row else None


def require_project(db, identifier):
    if not db.execute('SELECT 1 FROM project WHERE id=?', (identifier,)).fetchone() or (
        not _maintenance.get() and db.execute("SELECT 1 FROM sqlite_master WHERE name='project_trash'").fetchone()
        and db.execute('SELECT 1 FROM project_trash WHERE project_id=?', (identifier,)).fetchone()
    ):
        raise denied()
    return identifier


@contextmanager
def bind(identifier):
    token = _identity.set(identifier)
    try:
        yield
    finally:
        _identity.reset(token)


@contextmanager
def maintenance():
    """Startup recovery only; never exposed as an HTTP or model argument."""
    token = _maintenance.set(True)
    try:
        yield
    finally:
        _maintenance.reset(token)


def worker(target):
    """Capture separately for every submitted operation (a Context is not shared)."""
    context = copy_context()
    return lambda *args, **kwargs: context.run(target, *args, **kwargs)


def session_project(database, sid):
    with connect_database(database) as db:
        columns = {row[1] for row in db.execute('PRAGMA table_info(agent_session)')}
        if 'project_id' not in columns:
            return current(db)
        row = db.execute('SELECT project_id FROM agent_session WHERE id=?', (sid,)).fetchone()
        if not row:
            error = DataError('SESSION_NOT_FOUND', '会话不存在')
            error.status_code = 404
            raise error
        return require_project(db, row[0])


def owned(db, kind, identifier):
    """Return ownership without exposing whether a foreign identifier exists."""
    if not identifier:
        return False
    if _maintenance.get():
        return True
    project = current(db)
    if project is not None:
        require_project(db, project)
    if kind == 'model_ref':
        for table, domain in [('model_registry', 'model'), ('classification_model', 'classification_model')]:
            if db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone() and db.execute(f'SELECT 1 FROM {table} WHERE id=?', (str(identifier),)).fetchone():
                return owned(db, domain, identifier)
        return owned(db, 'experiment', identifier)
    direct = {'cube': 'dataset_registry', 'label': 'label', 'schema': 'label_schema',
              'classification_model': 'classification_model', 'target': 'sample_target',
              'session': 'agent_session'}
    if kind in direct:
        return bool(db.execute(f'SELECT 1 FROM {direct[kind]} WHERE id=? AND project_id=?',
                               (str(identifier), project)).fetchone())
    if kind == 'recipe':
        return bool(db.execute('SELECT 1 FROM preprocess_recipe r WHERE r.id=? AND '
            '(r.builtin=1 OR EXISTS(SELECT 1 FROM project_recipe p WHERE p.recipe_id=r.id AND p.project_id=?))',
            (str(identifier), project)).fetchone())
    if kind == 'recipe_version':
        row = db.execute('SELECT recipe_id FROM preprocess_recipe_version WHERE id=?', (str(identifier),)).fetchone()
        return bool(row and owned(db, 'recipe', row[0]))
    parents = {'annotation': ('annotation_version', 'cube_id', 'cube'),
               'preprocess': ('preprocess_run', 'cube_id', 'cube'),
               'model': ('model_registry', 'run_id', 'training'),
               'inference': ('inference_run', 'cube_id', 'cube')}
    if kind in parents:
        table, field, parent = parents[kind]
        if not db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
            return False
        row = db.execute(f'SELECT {field} FROM {table} WHERE id=?', (str(identifier),)).fetchone()
        if kind == 'model' and not row:
            return owned(db, 'classification_model', identifier)
        return bool(row and owned(db, parent, row[0]))
    if kind == 'training':
        row = db.execute('SELECT cube_ids FROM training_run WHERE id=?', (str(identifier),)).fetchone()
        cubes = json.loads(row[0]) if row else []
        return bool(cubes and all(owned(db, 'cube', cube) for cube in cubes))
    if kind == 'evaluation':
        row = db.execute('SELECT run_id FROM classification_evaluation WHERE id=?', (str(identifier),)).fetchone()
        return bool(row and owned(db, 'training', row[0]))
    if kind == 'classification_export':
        row = db.execute('SELECT evaluation_id FROM classification_export WHERE id=?', (str(identifier),)).fetchone()
        return bool(row and owned(db, 'evaluation', row[0]))
    if kind == 'training_job':
        row = db.execute('SELECT body FROM training_job WHERE id=?', (str(identifier),)).fetchone()
        if not row:
            return False
        try:
            check_document(db, json.loads(row[0]))
            return True
        except DataError:
            return False
    if kind in {'experiment', 'study'}:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='project_resource'").fetchone():
            return project is None
        row = db.execute('SELECT project_id FROM project_resource WHERE kind=? AND resource_id=?',
                         (kind, str(identifier))).fetchone()
        if kind == 'study':
            # Legacy drafts/archives are indexed from their session at startup.
            # An unknown ID must not become accessible just in the default project.
            return bool(row and row[0] == project)
        # Old filesystem archives stay with the legacy default project. They
        # are not assigned to whichever project first happens to open them.
        default = db.execute("SELECT id FROM project WHERE name='默认项目' ORDER BY created_at,id LIMIT 1").fetchone()
        return bool((row and row[0] == project) or (not row and default and default[0] == project))
    raise ValueError('Unknown project resource: '+kind)


def require(db, kind, identifier):
    if not owned(db, kind, identifier):
        raise denied()


def register(db, kind, identifier):
    """Claim once inside the resource's transaction; never transfer ownership.

    Repeated registration in the same project is safe, but a conflicting owner
    must fail rather than being hidden by INSERT OR IGNORE or the legacy lookup.
    The caller commits before exposing the resource to another connection/thread.
    """
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='project_resource'").fetchone():
        if current(db) is None:
            return  # Isolated numerical engine without a workspace database.
        raise RuntimeError('Project migration must precede resource creation')
    project = current(db)
    db.execute('INSERT INTO project_resource(kind,resource_id,project_id) VALUES (?,?,?) '
               'ON CONFLICT(kind,resource_id) DO NOTHING', (kind, str(identifier), project))
    owner = db.execute('SELECT project_id FROM project_resource WHERE kind=? AND resource_id=?',
                       (kind, str(identifier))).fetchone()
    if not owner or owner[0] != project:
        raise denied()


def filter_ids(db, kind, identifiers):
    return [identifier for identifier in identifiers if owned(db, kind, identifier)]


_FIELDS = {'cube_id': 'cube', 'dataset_id': 'cube', 'cube_ids': 'cube',
           'axis_cube_id': 'cube', 'selected_cube_id': 'cube',
           'annotation_version_id': 'annotation', 'annotation_version_ids': 'annotation',
           'annotation_id': 'annotation', 'preprocess_run_id': 'preprocess',
           'preprocess_run_ids': 'preprocess', 'recipe_id': 'recipe',
           'recipe_version_id': 'recipe_version', 'target_schema_id': 'schema',
           'schema_id': 'schema', 'label_id': 'label', 'model_id': 'model_ref',
           'evaluation_id': 'evaluation', 'inference_run_id': 'inference',
           'training_run_id': 'training', 'comparison_run_id': 'training', 'source_recipe_version_id': 'recipe_version',
           'experiment_id': 'experiment', 'base_experiment_id': 'experiment', 'study_id': 'study'}


def check_document(db, value):
    if isinstance(value, list):
        for item in value:
            check_document(db, item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == 'project_id' and item is not None and item != current(db):
                raise denied()
            if key in _FIELDS and item:
                for identifier in item if isinstance(item, list) else [item]:
                    require(db, _FIELDS[key], identifier)
            elif isinstance(item, (dict, list)):
                check_document(db, item)


def checked(kind, argument='identifier'):
    """Guard public domain getters too; HTTP/tool validation is not the boundary."""
    import inspect
    def decorate(function):
        signature = inspect.signature(function)
        @wraps(function)
        def call(self, *args, **kwargs):
            values = signature.bind(self, *args, **kwargs).arguments
            with connect_database(self.database) as db:
                require(db, kind, values[argument])
            return function(self, *args, **kwargs)
        return call
    return decorate


def initialize(db):
    """Add metadata only. Never split existing datasets or rewrite artifacts."""
    from spectrumagent.annotation.labels import now
    default = db.execute("SELECT id FROM project WHERE name='默认项目' ORDER BY created_at,id LIMIT 1").fetchone()[0]
    columns = {row[1] for row in db.execute('PRAGMA table_info(agent_session)')}
    first_migration = not db.execute("SELECT 1 FROM sqlite_master WHERE name='desktop_project'").fetchone()
    if 'project_id' not in columns:
        db.execute('ALTER TABLE agent_session ADD COLUMN project_id TEXT REFERENCES project(id)')
    db.execute('UPDATE agent_session SET project_id=? WHERE project_id IS NULL', (default,))
    from spectrumagent.agent.step_plan import initialize as initialize_plan
    initialize_plan(db)
    db.execute('CREATE INDEX IF NOT EXISTS session_project_list ON agent_session(project_id,updated_at,id)')
    db.execute('''CREATE TABLE IF NOT EXISTS desktop_project (
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), project_id TEXT NOT NULL REFERENCES project(id))''')
    db.execute('INSERT OR IGNORE INTO desktop_project VALUES(1,?)', (default,))
    db.execute('''CREATE TABLE IF NOT EXISTS project_trash (
        project_id TEXT PRIMARY KEY REFERENCES project(id), deleted_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS project_resource (
        kind TEXT NOT NULL CHECK(kind IN ('experiment','study')), resource_id TEXT NOT NULL,
        project_id TEXT NOT NULL REFERENCES project(id), PRIMARY KEY(kind,resource_id))''')
    # Existing unassociated custom recipes belong to the legacy project.
    if first_migration and db.execute("SELECT 1 FROM sqlite_master WHERE name='project_recipe'").fetchone():
        db.execute('INSERT OR IGNORE INTO project_recipe(project_id,recipe_id,selected_at) '
                   'SELECT ?,id,? FROM preprocess_recipe r WHERE builtin=0 AND NOT EXISTS '
                   '(SELECT 1 FROM project_recipe p WHERE p.recipe_id=r.id)', (default, now()))
    db.execute('''CREATE TRIGGER IF NOT EXISTS session_project_required BEFORE INSERT ON agent_session
        WHEN NEW.project_id IS NULL BEGIN SELECT RAISE(ABORT,'SESSION_PROJECT_REQUIRED'); END''')
    db.execute('''CREATE TRIGGER IF NOT EXISTS session_project_immutable BEFORE UPDATE OF project_id ON agent_session
        WHEN NEW.project_id IS NOT OLD.project_id BEGIN SELECT RAISE(ABORT,'SESSION_PROJECT_IMMUTABLE'); END''')


def backup_before_migration(database):
    """Consistent SQLite backup before the first upgrade of an existing workspace.

    The source connection uses SQLite's backup API, which includes committed WAL
    content. It never copies a live main file independently of its WAL.
    """
    from pathlib import Path
    import sqlite3
    from spectrumagent.storage import guard
    if not Path(database).exists():
        return None
    with connect_database(database) as source:
        columns = {r[1] for r in source.execute('PRAGMA table_info(agent_session)')}
        if not columns or 'project_id' in columns or not source.execute('SELECT 1 FROM agent_session LIMIT 1').fetchone():
            return None
        destination = Path(database).parent / 'backups' / ('before-projects-'+uuid4().hex+'.sqlite3')
        guard.mkdir(destination.parent, parents=True, exist_ok=True)
        with sqlite3.connect(guard.resolve_write(destination, kind='PROJECT_MIGRATION_BACKUP')) as backup:
            source.backup(backup)
        return destination


class Projects:
    def __init__(self, database):
        self.database = database

    def list(self):
        with connect_database(self.database) as db:
            rows = [dict(zip(('id','name','deleted_at','dataset_count','session_count'), r)) for r in db.execute('''SELECT p.id,p.name,t.deleted_at,
                (SELECT COUNT(*) FROM dataset_registry d WHERE d.project_id=p.id) AS dataset_count,
                (SELECT COUNT(*) FROM agent_session s WHERE s.project_id=p.id) AS session_count
                FROM project p LEFT JOIN project_trash t ON t.project_id=p.id ORDER BY p.created_at,p.id''')]
            return {'current_project_id': current(db), 'projects': [r for r in rows if r['deleted_at'] is None],
                    'deleted_projects': [r for r in rows if r['deleted_at'] is not None]}

    def create(self, name):
        from spectrumagent.annotation.labels import now
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100 or any(ord(c) < 32 for c in name):
            raise DataError('INVALID_PROJECT_NAME', '项目名称须为 1 至 100 个可见字符')
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            if any(r[0].casefold() == name.strip().casefold() for r in db.execute('SELECT name FROM project')):
                raise DataError('PROJECT_NAME_EXISTS', '项目名称已存在')
            identifier = str(uuid4())
            db.execute('INSERT INTO project(id,name,created_at) VALUES(?,?,?)', (identifier, name.strip(), now()))
            db.execute("INSERT INTO label_schema(id,project_id,name,tree_path,field_type,created_at) VALUES(?,?,'材料','材料','enum',?)",
                       (str(uuid4()), identifier, now()))
        return {'id': identifier, 'name': name.strip()}

    def select(self, identifier):
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            require_project(db, identifier)
            db.execute('UPDATE desktop_project SET project_id=? WHERE singleton=1', (identifier,))
        return {'current_project_id': identifier}

    def _preview(self, db, identifier):
        from hashlib import sha256
        require_project(db, identifier)
        row = db.execute('SELECT id,name FROM project WHERE id=?', (identifier,)).fetchone()
        result = dict(id=row[0], name=row[1])
        for key, table in [('dataset_count', 'dataset_registry'), ('session_count', 'agent_session'),
                           ('label_count', 'label'), ('recipe_count', 'project_recipe'),
                           ('experiment_count', 'project_resource')]:
            result[key] = db.execute(f'SELECT COUNT(*) FROM {table} WHERE project_id=?', (identifier,)).fetchone()[0]
        result['confirmation_token'] = sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        return result

    def deletion_preview(self, identifier):
        with connect_database(self.database) as db:
            return self._preview(db, identifier)

    def delete(self, identifier, confirm_name, confirmation_token, *, is_busy=None):
        with project_change(self.database, identifier):
            return self._delete(identifier, confirm_name, confirmation_token, is_busy=is_busy)

    def _delete(self, identifier, confirm_name, confirmation_token, *, is_busy=None):
        """Reversible removal: never delete original files, audit rows or artifacts."""
        from spectrumagent.annotation.labels import now
        def fail(code, message):
            error = DataError(code, message)
            error.status_code = 409
            raise error
        with connect_database(self.database) as db:
            require_project(db, identifier)
            sessions = db.execute('SELECT id,updated_at FROM agent_session WHERE project_id=? ORDER BY id', (identifier,)).fetchall()
        # Check in-memory queues before taking the DB write lock: workers take
        # their service lock before writing SQLite, so reverse order deadlocks.
        if is_busy and is_busy(identifier, [r[0] for r in sessions]):
            fail('PROJECT_BUSY', '项目仍有运行或排队的任务，请先完成或取消任务')
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            preview = self._preview(db, identifier)
            if confirm_name != preview['name'] or confirmation_token != preview['confirmation_token']:
                fail('PROJECT_DELETE_REVIEW_CHANGED', '项目名称或资源数量已变化，请重新查看删除说明并确认')
            if sessions != db.execute('SELECT id,updated_at FROM agent_session WHERE project_id=? ORDER BY id', (identifier,)).fetchall():
                fail('PROJECT_BUSY', '项目刚有新的操作，请核对后重试')
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('agent_session_request', 'experiment_task'):
                if table in tables and db.execute(f'''SELECT 1 FROM {table} r JOIN agent_session s ON s.id=r.session_id
                    WHERE s.project_id=? AND r.status IN ('queued','running') LIMIT 1''', (identifier,)).fetchone():
                    fail('PROJECT_BUSY', '项目仍有运行或排队的任务，请先完成或取消任务')
            for table in ('preprocess_run', 'inference_run'):
                if table in tables and db.execute(f'''SELECT 1 FROM {table} r JOIN dataset_registry d ON d.id=r.cube_id
                    WHERE d.project_id=? AND r.status IN ('pending','running') LIMIT 1''', (identifier,)).fetchone():
                    fail('PROJECT_BUSY', '项目仍有预处理或推理任务，请先完成任务')
            if 'training_run' in tables and db.execute('''SELECT 1 FROM training_run r,
                json_each(r.cube_ids) c JOIN dataset_registry d ON d.id=c.value
                WHERE d.project_id=? AND r.status IN ('pending','running') LIMIT 1''', (identifier,)).fetchone():
                fail('PROJECT_BUSY', '项目仍有训练任务，请先完成任务')
            if 'training_job' in tables and db.execute('''SELECT 1 FROM training_job j,
                json_each(j.body,'$.cube_ids') c JOIN dataset_registry d ON d.id=c.value
                WHERE d.project_id=? AND json_extract(j.snapshot,'$.status') IN ('queued','running') LIMIT 1''', (identifier,)).fetchone():
                fail('PROJECT_BUSY', '项目仍有分类训练任务，请先完成或取消任务')
            remaining = db.execute('''SELECT id FROM project p WHERE id<>?
                AND NOT EXISTS(SELECT 1 FROM project_trash t WHERE t.project_id=p.id)
                ORDER BY created_at,id LIMIT 1''', (identifier,)).fetchone()
            if not remaining:
                fail('LAST_PROJECT', '至少保留一个可用项目，请先新建其他项目')
            db.execute('INSERT INTO project_trash(project_id,deleted_at) VALUES(?,?)', (identifier, now()))
            db.execute('UPDATE desktop_project SET project_id=? WHERE singleton=1 AND project_id=?', (remaining[0], identifier))
            selected = db.execute('SELECT project_id FROM desktop_project WHERE singleton=1').fetchone()[0]
        return {'project_id': identifier, 'deleted': True, 'current_project_id': selected}

    def restore(self, identifier):
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT id,name FROM project WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise denied()
            db.execute('DELETE FROM project_trash WHERE project_id=?', (identifier,))
            return dict(id=row[0], name=row[1])

    def migration_preview(self):
        """Read-only inventory: no guessing a target project from folder names."""
        with connect_database(self.database) as db:
            return {'status': 'preview_only', 'datasets': [dict(id=r[0], project_id=r[1], name=json.loads(r[2]).get('name'))
                for r in db.execute('SELECT id,project_id,payload FROM dataset_registry ORDER BY rowid')],
                'sessions': [dict(id=r[0], project_id=r[1]) for r in db.execute('SELECT id,project_id FROM agent_session')],
                'labels': [dict(id=r[0], project_id=r[1], code=r[2], name=r[3])
                    for r in db.execute('SELECT id,project_id,code,name FROM label WHERE deleted_at IS NULL')]}
