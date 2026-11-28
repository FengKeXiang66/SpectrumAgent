"""Immutable session scope, bounded management views and availability checks."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from uuid import UUID, uuid4

from backend.database import connect_database
from spectrumagent.data import DataError
from . import context as memory
from .skill import active_skill
from .state import AgentStore, _failure, _now, _rows


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise _failure('INVALID_REQUEST', '需要明确的 UUID') from None


class SessionService:
    TOKEN_SECONDS = 300
    CACHE_SECONDS = 30

    def __init__(self, database, versions, boot_id, *, clock=time.time):
        self.database, self.versions = database, versions
        self.registry = versions.registry if versions is not None else None
        self.boot_id, self.clock = boot_id, clock
        self.secret = secrets.token_bytes(32)
        self.store = AgentStore(database)
        self.availability_cache = {}
        self.authorization_records = {}  # Engine lifetime only; never model-owned state.
        self.annotation_targets = {}  # Pending member snapshots confer no operation permission.
        self.flow_requests = {}

    def _sign(self, data):
        body = base64.urlsafe_b64encode(canonical(data).encode()).decode().rstrip('=')
        return body + '.' + hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()

    def _decode(self, token):
        try:
            body, signature = token.split('.')
            if not hmac.compare_digest(signature, hmac.new(self.secret, body.encode(), hashlib.sha256).hexdigest()):
                raise ValueError()
            return json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        except (ValueError, TypeError, AttributeError):
            raise _failure('INVALID_REQUEST', '确认凭据无效，请重新核验', 409) from None

    def scope(self, session_id):
        self.store.session(session_id)
        with connect_database(self.database) as db:
            if db.execute('SELECT 1 FROM agent_session_archive WHERE session_id=?', (session_id,)).fetchone():
                raise _failure('SESSION_ARCHIVED', '会话已从列表移除', 404)
            rows = _rows(db, 'SELECT * FROM agent_session_scope WHERE session_id=?', (session_id,))
        if not rows:
            raise _failure('SESSION_SCOPE_MISSING', '会话范围尚未迁移', 409)
        return rows[0]

    def _members(self, session_id):
        with connect_database(self.database) as db:
            return _rows(db, 'SELECT ordinal,cube_id,content_hash FROM agent_session_member WHERE session_id=? ORDER BY ordinal', (session_id,))

    def availability(self, cube):
        if self.registry is None:
            return {'available': False, 'reason': 'MEMBER_UNAVAILABLE'}
        try:
            dataset, _ = self.registry.readable(cube)
            # Readers may defer mmap access. Open the actual registered source,
            # not a guessed ENVI sibling. This is O(1) I/O, never a content hash.
            with open(dataset.data_path, 'rb') as stream:
                if not stream.read(1):
                    raise OSError()
                stream.seek(-1, 2)
                if not stream.read(1):
                    raise OSError()
            return {'available': True, 'reason': None}
        except (DataError, OSError, ValueError):
            return {'available': False, 'reason': 'MEMBER_UNAVAILABLE'}

    def create(self, scope=None, request_id=None, partial_confirmation_token=None, project_id=None):
        # 2026-11-13 simplification: only global sessions; work sessions removed.
        scope = scope or {'kind': 'global'}
        kind = scope['kind']
        if kind != 'global' or partial_confirmation_token is not None:
            raise _failure('INVALID_REQUEST','只支持全局会话')
        key = identifier(request_id) if request_id else None
        from spectrumagent.projects import current, require_project
        with connect_database(self.database) as db:
            project_id = require_project(db, project_id or current(db))
        payload_hash = digest({'scope':scope,'project_id':project_id,'partial_confirmation_token':partial_confirmation_token})
        # Completed idempotency precedes availability/token expiration checks.
        if key:
            with connect_database(self.database) as db:
                old = db.execute('SELECT p.session_id,p.creation_payload_hash,s.project_id FROM agent_session_scope p JOIN agent_session s ON s.id=p.session_id WHERE p.creation_key=?', (key,)).fetchone()
            if old:
                if old[1] != payload_hash and not (old[2] == project_id and old[1] == digest({'scope':scope,'partial_confirmation_token':partial_confirmation_token})):
                    raise _failure('REQUEST_ID_CONFLICT', '创建请求已用于不同范围', 409)
                return self.created(old[0])
        audit = {}
        lock = self.registry.lock if self.registry else __import__('contextlib').nullcontext()
        with lock, connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                old = db.execute('SELECT p.session_id,p.creation_payload_hash,s.project_id FROM agent_session_scope p JOIN agent_session s ON s.id=p.session_id WHERE p.creation_key=?', (key,)).fetchone()
                if old:
                    if old[1] != payload_hash and not (old[2] == project_id and old[1] == digest({'scope':scope,'partial_confirmation_token':partial_confirmation_token})):
                        raise _failure('REQUEST_ID_CONFLICT', '创建请求已用于不同范围', 409)
                    return self.created(old[0])
            version, now, sid = active_skill(db), _now(), str(uuid4())
            db.execute('INSERT INTO agent_session(id,title,skill_version_id,created_at,updated_at,project_id) VALUES (?,?,?,?,?,?)', (sid, '', version['id'], now, now, project_id))
            db.execute('INSERT INTO agent_session_scope(session_id,scope_kind,dataset_version_ref,version_content_hash,member_count,creation_key,creation_payload_hash,creation_audit_json) VALUES (?,?,?,?,?,?,?,?)',
                       (sid, kind, None, None, 0, key, payload_hash, canonical(audit)))
        return self.created(sid)

    def created(self, sid):
        row = self.store.session(sid)
        with connect_database(self.database) as db:
            name = db.execute('SELECT name FROM project WHERE id=?', (row['project_id'],)).fetchone()[0]
        return {k: row[k] for k in ('id', 'title', 'skill_version_id', 'created_at', 'project_id')} | {'project_name': name}

    def members(self, sid, *, after=0, limit=50):
        self.scope(sid)
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise _failure('INVALID_REQUEST', '成员分页参数无效')
        with connect_database(self.database) as db:
            rows = _rows(db, 'SELECT ordinal,cube_id FROM agent_session_member WHERE session_id=? AND ordinal>? ORDER BY ordinal LIMIT ?', (sid, after, limit+1))
            for row in rows[:limit]:
                stored = db.execute("SELECT json_extract(payload,'$.name') FROM dataset_registry WHERE id=?", (row['cube_id'],)).fetchone()
                from spectrumagent.api.registry import safe_name
                row['display_name'] = safe_name(stored[0]) if stored else '缺失样品'
                row.update(self.availability(row['cube_id']))
                row['ref'] = 'D' + str(row['ordinal'])
        return {'members': rows[:limit], 'next_after': rows[limit-1]['ordinal'] if len(rows)>limit else None}

    def _counts(self, sid, refresh):
        scope = self.scope(sid)
        if scope['scope_kind'] == 'global':
            ids = []
            if self.registry is not None:
                with connect_database(self.database) as db:
                    ids = [r[0] for r in db.execute('SELECT id FROM dataset_registry WHERE project_id=? ORDER BY rowid', (self.store.session(sid)['project_id'],))]
            count = sum(self.availability(cube)['available'] for cube in ids) if refresh else None
            return {'available_members': count, 'total_members': len(ids),
                    'availability_status': ('unknown' if count is None else 'available' if count == len(ids)
                                            else 'partial' if count else 'unavailable'),
                    'availability_checked_at': _now() if refresh else None}
        cached = self.availability_cache.get(sid)
        if not refresh:
            if cached and self.clock()-cached[0] <= self.CACHE_SECONDS:
                return cached[1]
            return {'available_members': None, 'total_members': scope['member_count'], 'availability_status': 'unknown', 'availability_checked_at': None}
        count=0
        with connect_database(self.database) as db:
            cursor=db.execute('SELECT cube_id FROM agent_session_member WHERE session_id=? ORDER BY ordinal',(sid,))
            while page:=cursor.fetchmany(100):
                count+=sum(self.availability(row[0])['available'] for row in page)
        total=scope['member_count']
        result = {'available_members': count, 'total_members': total, 'availability_checked_at': _now(),
                  'availability_status': 'available' if count==total else 'partial' if count else 'unavailable'}
        self.availability_cache[sid] = (self.clock(), result)
        # Cache bounds are independent of total persistent session count.
        if len(self.availability_cache)>128:
            self.availability_cache.pop(next(iter(self.availability_cache)))
        return result

    def detail(self, sid, *, refresh=True):
        scope, row = self.scope(sid), self.store.session(sid)
        context = memory.upgrade_context(json.loads(row['context_json']))
        selected = context.get('selected_cube_id')
        with connect_database(self.database) as db:
            stored_focus = db.execute('SELECT cube_id FROM agent_canvas_focus WHERE session_id=?', (sid,)).fetchone()
        focus = ({'cube_id': stored_focus[0]} if stored_focus[0] else {}) if stored_focus else context.get('canvas_focus') or {}
        if focus.get('cube_id') and not self.availability(focus['cube_id'])['available']:
            focus = {}
        selected_ordinal=None
        if selected:
            with connect_database(self.database) as db:
                member=db.execute('SELECT ordinal FROM agent_session_member WHERE session_id=? AND cube_id=?',(sid,selected)).fetchone()
            if scope['scope_kind']=='dataset_version' and not member or not self.availability(selected)['available']:
                selected = None
            elif member:
                selected_ordinal=member[0]
        pending = self.store.pending(sid)
        with connect_database(self.database) as db:
            request = _rows(db, "SELECT request_id,status,boot_id,events_complete FROM agent_session_request WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (sid,))
            watermark = db.execute('SELECT COALESCE(MAX(seq),0) FROM agent_session_event WHERE session_id=?', (sid,)).fetchone()[0]
        flow = context.get('annotation_flow_request')
        return {**self.created(sid), 'updated_at': row['updated_at'], 'boot_id': self.boot_id,
                **({'annotation_flow': {'task_id': flow['response']['task_id'],
                    'request_id': flow['request_id'],
                    'cube_ids': self.authorization_records.get(flow['authorization_id'], {}).get('cube_ids', []),
                    'authorization_id': flow['authorization_id'],
                    'mode': flow['mode']}} if flow else {}),
                'scope': {'kind': scope['scope_kind'], 'dataset_version_id': scope['dataset_version_ref'], 'member_count': scope['member_count']},
                'selected_cube_id': selected, 'selected_ordinal':selected_ordinal,
                'canvas_focus': focus,
                'history_watermark': watermark, **self._counts(sid, refresh),
                'pending': self.pending_view(pending), 'request': request[0] if request else None}

    def pending_view(self, pending):
        if not pending:
            return None
        row, check = pending
        def checked_view(value, references):
            from spectrumagent.projects import bind, check_document, session_project
            try:
                with bind(session_project(self.database,row['session_id'])), connect_database(self.database) as db:
                    check_document(db,references)
            except DataError:
                value.update(blocked=True, reason='资源归属或引用已变化，原确认不可执行；请拒绝旧操作后重新建立并审阅方案。')
            return value
        if row['status']=='plan_check':
            calls, _ = self.store.effective_calls(row['id'])
            return checked_view({'kind':'plan', 'plan_id':row['id'], 'reason':'恢复的执行计划，批准前将重新核验',
                    'steps':[{'seq':i,'tool':c['name'],'summary':{},'gpu':False,'estimate_ms':None} for i,c in enumerate(calls,1)]}, [c['arguments'] for c in calls])
        with connect_database(self.database) as db:
            step = db.execute('SELECT tool,result_summary,arguments_json FROM agent_step WHERE id=?', (check,)).fetchone()
        summary={k:v for k,v in json.loads(step[1]).items() if k in {'cube_id','revision','class_code','overwrite','dataset_version_id','available_members','total_members','availability_checked_at'}}
        return checked_view({'kind':'human_check','check_id':check,'tool':step[0], 'summary':summary,
                'reason':'恢复的待确认操作，批准前将重新核验'}, json.loads(step[2]))

    def archive(self, sid, *, experiment_active=None):
        """Remove from management view without deleting any audit row."""
        identifier(sid)
        with connect_database(self.database) as db:
            original = db.execute('SELECT updated_at FROM agent_session WHERE id=?', (sid,)).fetchone()
        if not original:
            raise _failure('INVALID_REQUEST', '会话不存在', 404)
        if experiment_active and experiment_active(sid):
            raise _failure('SESSION_BUSY', '请先完成或取消本会话的训练、寻优或推理任务', 409)
        training = getattr(self.registry, '_training_jobs', None)
        if training:
            with training.lock:
                if any(j['owner'] == sid and j['receipt']['status'] in ('queued', 'running') for j in training.jobs.values()):
                    raise _failure('SESSION_BUSY', '请先完成或取消本会话的分类训练', 409)
        tasks = getattr(self, 'annotation_tasks', None)
        if tasks:
            with tasks.lock:
                if any(task['owner_session_id'] == sid and task['task_status'] in {'queued','running'} for task in tasks.receipts.values()):
                    raise _failure('SESSION_BUSY', '请先完成或取消本会话的后台任务', 409)
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            # A just-finished request may have submitted work since the in-memory task check.
            updated = db.execute('SELECT updated_at FROM agent_session WHERE id=?', (sid,)).fetchone()
            if (updated != original or
                    db.execute("SELECT 1 FROM agent_session_request WHERE session_id=? AND status='running'", (sid,)).fetchone()):
                raise _failure('SESSION_BUSY', '请先结束当前执行再移除会话', 409)
            db.execute('INSERT OR IGNORE INTO agent_session_archive(session_id,archived_at) VALUES(?,?)', (sid, _now()))
        return {'session_id': sid, 'archived': True}

    def list(self, *, kind=None, dataset_version_id=None, limit=20, cursor=None, project_id=None):
        if type(limit) is not int or not 1<=limit<=50 or kind not in (None,'global','dataset_version'):
            raise _failure('INVALID_REQUEST', '会话列表参数无效')
        if dataset_version_id:
            identifier(dataset_version_id)
        from spectrumagent.projects import current, require_project
        with connect_database(self.database) as db:
            project_id = require_project(db, project_id or current(db))
        filters = {'kind':kind,'dataset_version_id':dataset_version_id,'project_id':project_id}
        boundary = self._decode(cursor) if cursor else None
        if boundary and boundary.get('filters')!=filters:
            raise _failure('INVALID_REQUEST', '游标不属于当前查询')
        where, args = ["NOT EXISTS (SELECT 1 FROM agent_session_archive a WHERE a.session_id=s.id)"], []
        where.append('s.project_id=?');args.append(project_id)
        if kind:
            where.append('p.scope_kind=?');args.append(kind)
        if dataset_version_id:
            where.append('p.dataset_version_ref=?');args.append(dataset_version_id)
        if boundary:
            where.append('(s.updated_at,s.id)<(?,?)');args.extend(boundary['last'])
        with connect_database(self.database) as db:
            rows = _rows(db, '''SELECT s.id,s.title,s.created_at,s.updated_at,s.project_id,
                EXISTS(SELECT 1 FROM agent_round r WHERE r.session_id=s.id AND r.status IN ('human_check','plan_check')) AS pending,
                COALESCE((SELECT MAX(seq) FROM agent_session_event e WHERE e.session_id=s.id),0) AS history_watermark,
                (SELECT json_object('request_id',r.request_id,'status',r.status,'boot_id',r.boot_id,'events_complete',r.events_complete)
                 FROM agent_session_request r WHERE r.session_id=s.id ORDER BY r.created_at DESC,r.rowid DESC LIMIT 1) AS request
                FROM agent_session s JOIN agent_session_scope p ON s.id=p.session_id
                WHERE '''+' AND '.join(where)+' ORDER BY s.updated_at DESC,s.id DESC LIMIT ?', (*args,limit+1))
        items = rows[:limit]
        for item in items:
            item['pending'] = bool(item['pending'])
            item['request'] = json.loads(item['request']) if item['request'] else None
        return {'sessions':items, 'next_cursor': self._sign({'filters':filters,
                    'last':[items[-1]['updated_at'],items[-1]['id']]}) if len(rows)>limit else None}

    def select(self, sid, cube_id):
        scope = self.scope(sid)
        if cube_id is not None:
            from spectrumagent.projects import bind, require, session_project
            with bind(session_project(self.database, sid)), connect_database(self.database) as db:
                require(db, 'cube', cube_id)
        if cube_id is not None:
            identifier(cube_id)
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM agent_session_request WHERE session_id=? AND status='running'", (sid,)).fetchone() or db.execute("SELECT 1 FROM agent_round WHERE session_id=? AND status IN ('running','human_check','plan_check')", (sid,)).fetchone():
                raise _failure('SESSION_BUSY','请先结束当前执行或待确认操作',409)
            if cube_id and scope['scope_kind']=='dataset_version' and not db.execute('SELECT 1 FROM agent_session_member WHERE session_id=? AND cube_id=?',(sid,cube_id)).fetchone():
                raise _failure('SESSION_SCOPE_MISMATCH','样品不属于当前会话，请进入全局或对应工作会话',409)
            if cube_id and not self.availability(cube_id)['available']:
                raise _failure('SESSION_MEMBER_UNAVAILABLE','样品当前不可用',409)
            db.execute('INSERT INTO agent_canvas_focus(session_id,cube_id,updated_at) VALUES(?,?,?) '
                       'ON CONFLICT(session_id) DO UPDATE SET cube_id=excluded.cube_id,updated_at=excluded.updated_at', (sid,cube_id,_now()))
        return self.detail(sid)

    def remember_canvas(self, sid, cube_id):
        """Canvas metadata is independent of model/task context saves."""
        with connect_database(self.database) as db:
            db.execute('INSERT INTO agent_canvas_focus(session_id,cube_id,updated_at) VALUES(?,?,?) '
                       'ON CONFLICT(session_id) DO UPDATE SET cube_id=excluded.cube_id,updated_at=excluded.updated_at',
                       (sid,cube_id,_now()))
