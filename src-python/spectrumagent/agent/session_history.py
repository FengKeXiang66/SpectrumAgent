"""Display journal and finite request leases, separate from execution ledgers."""
import json
from threading import RLock
from uuid import uuid4

from backend.database import connect_database
from .sessions import canonical, digest, identifier
from .state import _failure, _now, _rows
from .execution import RequestCancelled, RequestControl


MAX_EVENT_BYTES = 256 * 1024
PAGE_BYTES = 1024 * 1024
EVENTS = {'step','plan','human_check','workspace','clarify','done','error','progress'}


class SessionHistory:
    def __init__(self, service):
        self.service, self.database, self.boot_id = service, service.database, service.boot_id
        self.controls = {}
        self.lock = RLock()

    def request_state(self, sid, request):
        self.service.scope(sid)
        with connect_database(self.database) as db:
            rows = _rows(db, 'SELECT request_id,status,events_complete,boot_id FROM agent_session_request WHERE session_id=? AND request_id=?', (sid, request))
        if not rows:
            raise _failure('REQUEST_NOT_FOUND', '请求不存在', 404)
        with self.lock:
            control = self.controls.get((sid, request))
            return {'session_id': sid, **rows[0], 'cancel_requested': bool(control and control.cancelled.is_set()),
                    'phase': control.phase if control else rows[0]['status']}

    def cancel(self, sid, request):
        self.service.scope(sid)
        with self.lock:
            state = self.request_state(sid, request)
            if state['status'] == 'running':
                control = self.controls.get((sid, request))
                if control is None:
                    raise _failure('REQUEST_NOT_CANCELABLE', '请求执行状态未知，请核对执行记录', 409)
                control.cancel()
            return self.request_state(sid, request)

    @staticmethod
    def _append(db, sid, kind, payload, request=None, *, origin='live', source_key):
        text=canonical(payload)
        if len(text.encode())>MAX_EVENT_BYTES:
            # Never silently persist a partially reconstructable executable card.
            raise _failure('SESSION_EVENT_LIMIT','显示记录超过单项上限，执行状态须从账本核对',409)
        if db.execute('SELECT 1 FROM agent_session_event WHERE session_id=? AND source_key=?',(sid,source_key)).fetchone():return
        seq=db.execute('SELECT COALESCE(MAX(seq),0)+1 FROM agent_session_event WHERE session_id=?',(sid,)).fetchone()[0]
        db.execute('INSERT INTO agent_session_event(session_id,seq,request_id,kind,payload_json,created_at,origin,source_key) VALUES (?,?,?,?,?,?,?,?)',
                   (sid,seq,request,kind,text,_now(),origin,source_key))

    def append(self, sid, kind, payload, request, source_key):
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            self._append(db,sid,kind,payload,request,source_key=source_key)

    def startup(self):
        """Old running requests are unknown, not rolled back or re-executed."""
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE agent_session_request SET status='interrupted',finished_at=?,events_complete=0 WHERE status='running' AND boot_id<>?",(_now(),self.boot_id))
            db.execute("UPDATE agent_round SET status='error' WHERE status='running'")
        # Best-effort legacy projection: only actual user/answer/status/step
        # fields; never provider responses, arguments or invented old events.
        with connect_database(self.database) as db:
            sessions=[r[0] for r in db.execute('SELECT id FROM agent_session ORDER BY id')]
        for sid in sessions:self.project_legacy(sid)

    def project_legacy(self, sid):
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            last=0
            while True:
                rounds=_rows(db,'SELECT id,seq,turn_id,user_message,assistant_content,status FROM agent_round WHERE session_id=? AND seq>? ORDER BY seq LIMIT 100',(sid,last))
                if not rounds:break
                for row in rounds:
                    turn=row['turn_id'] or row['id']
                    # Live turns already have their true display records.
                    if db.execute("SELECT 1 FROM agent_session_event WHERE session_id=? AND origin='live'",(sid,)).fetchone():
                        return
                    if row['user_message']:
                        self._append(db,sid,'user',{'content':row['user_message'],'incomplete':True},origin='legacy_projection',source_key='legacy:user:'+turn)
                    steps=_rows(db,'SELECT id,seq,tool,status,result_summary FROM agent_step WHERE round_id=? ORDER BY seq',(row['id'],))
                    for step in steps:
                        # Old execution records are a partial projection, never
                        # a claim that every original display event was saved.
                        value=json.loads(step['result_summary'])
                        from .llm import _egress_blocked
                        summary={k:v for k,v in value.items() if type(v) in (str,int,float,bool) or v is None}
                        summary={k:v for k,v in summary.items() if k not in {'path','filename','partial_confirmation_token','geometry','spectra'} and not _egress_blocked({k:v})}
                        self._append(db,sid,'step',{'seq':step['seq'],'tool':step['tool'],'status':step['status'],
                            'result_summary':summary,'incomplete':True},origin='legacy_projection',source_key='legacy:step:'+step['id'])
                    if row['assistant_content'] is not None:
                        self._append(db,sid,'done',{'content':row['assistant_content'],'incomplete':True},origin='legacy_projection',source_key='legacy:answer:'+row['id'])
                    elif row['status']=='error':
                        self._append(db,sid,'error',{'code':'LEGACY_INCOMPLETE','detail':'旧账本未保存完整显示记录，请查看执行记录','incomplete':True},origin='legacy_projection',source_key='legacy:state:'+row['id'])
                last=rounds[-1]['seq']

    def page(self, sid, *, before=None, after=None, limit=50):
        self.service.scope(sid)
        if before is not None and after is not None or type(limit) is not int or not 1<=limit<=100:
            raise _failure('INVALID_REQUEST','历史游标互斥且须有界')
        if any(x is not None and (type(x) is not int or x<0) for x in (before,after)):
            raise _failure('INVALID_REQUEST','历史游标无效')
        with connect_database(self.database) as db:
            db.execute('BEGIN')
            watermark=db.execute('SELECT COALESCE(MAX(seq),0) FROM agent_session_event WHERE session_id=?',(sid,)).fetchone()[0]
            condition=' AND seq>?' if after is not None else ' AND seq<?'
            boundary=after if after is not None else before if before is not None else watermark+1
            rows=_rows(db,'SELECT seq,request_id,kind,payload_json,created_at,origin FROM agent_session_event WHERE session_id=?'+condition+' ORDER BY seq '+('ASC' if after is not None else 'DESC')+' LIMIT ?', (sid,boundary,limit+1))
        selected=[];size=0
        for row in rows[:limit]:
            length=len(row['payload_json'].encode())
            if size+length>PAGE_BYTES:break
            size+=length;row['payload']=json.loads(row.pop('payload_json'));selected.append(row)
        has_more=len(selected)<len(rows)
        if after is None:selected.reverse()
        return {'session_id':sid,'events':selected,'watermark':watermark,'has_more':has_more,
                'next_before':selected[0]['seq'] if selected and after is None and has_more else None,
                'next_after':selected[-1]['seq'] if selected and after is not None else None}

    def start(self, sid, body, request_id=None):
        self.service.scope(sid)
        request=identifier(request_id) if request_id else str(uuid4())
        hashed=digest(body)
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            old=_rows(db,'SELECT * FROM agent_session_request WHERE session_id=? AND request_id=?',(sid,request))
            if old:
                row=old[0]
                if row['payload_hash']!=hashed:
                    raise _failure('REQUEST_ID_CONFLICT','请求编号已用于不同消息',409)
                return request,row
            if db.execute("SELECT 1 FROM agent_session_request WHERE session_id=? AND status='running'",(sid,)).fetchone():
                raise _failure('SESSION_BUSY','当前会话仍在执行',409)
            db.execute('INSERT INTO agent_session_request(session_id,request_id,payload_hash,input_kind,boot_id,status,created_at) VALUES (?,?,?,?,?,?,?)',
                       (sid,request,hashed,'content' if 'content' in body else 'decision',self.boot_id,'running',_now()))
        return request,None

    def finish(self, sid, request, status, complete):
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE agent_session_request SET status=?,finished_at=?,events_complete=? WHERE session_id=? AND request_id=? AND status='running'",(status,_now(),int(complete),sid,request))

    def replay(self, sid, request, old):
        if old['status'] not in {'completed','failed'} or not old['events_complete']:
            recovered = self.project_receipts(sid, request)
            if recovered:
                return iter(recovered)
            return iter([('error',{'code':'REQUEST_'+old['status'].upper(),'detail':'请求状态需核对，请读取详情和历史；不会自动重做'})])
        with connect_database(self.database) as db:
            rows=db.execute("SELECT kind,payload_json FROM agent_session_event WHERE session_id=? AND request_id=? AND kind NOT IN ('user','decision') ORDER BY seq",(sid,request)).fetchall()
        return iter((kind,json.loads(payload)) for kind,payload in rows)

    def project_receipts(self, sid, request):
        """Only committed business facts; never reconstruct a lost model reply."""
        with connect_database(self.database) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='business_submission'").fetchone():
                return []
            rows = _rows(db, 'SELECT o.* FROM business_operation o JOIN business_submission s USING(submission_ref) '
                         'WHERE o.owner_session_id=? AND s.source_request_id=? ORDER BY o.created_at,o.action_ref', (sid,request))
        events = []
        for index, row in enumerate(rows, 1):
            summary = {'operation_id':row['operation_id'], 'status':row['status'], 'recovered':True}
            result = json.loads(row['receipt_json']) if row['receipt_json'] else {}
            if row['run_id']:
                summary['run_id'] = row['run_id']
            if row['kind'] == 'preprocess.recipe_create' and result:
                summary['recipe_id'] = result['id']
                summary['recipe_version_id'] = result['versions'][0]['id']
            elif row['kind'] == 'preprocess.recipe_version_add' and result:
                summary.update(recipe_id=result['recipe_id'], recipe_version_id=result['id'])
            elif row['kind'] == 'preprocess.draft_save' and result:
                summary.update(recipe_id=result['recipe_id'],recipe_version_id=result['recipe_version_id'],revision=result['revision'])
            elif row['kind'] == 'preprocess.draft_execute' and result:
                summary.update(succeeded=result['succeeded'],failed=result['failed'])
            payload = {'seq':index, 'tool':row['kind'], 'status':'ok' if row['status']=='succeeded' else 'error' if row['status']=='failed' else 'pending', 'result_summary':summary, 'operation_receipt':True}
            with connect_database(self.database) as db:
                db.execute('BEGIN IMMEDIATE')
                self._append(db, sid, 'step', payload, request, origin='business_receipt',
                             source_key='operation:' + row['operation_id'] + ':' + row['status'])
            events.append(('step',payload))
        if events:
            terminal = all(row['status'] in {'succeeded','failed'} for row in rows)
            events.append(('done',{'content':'已恢复业务回执；原始助手回复未完整保存。' + ('请核对执行日志。' if terminal else '部分操作需要核对，不会自动重做。'),
                                  'step_count':len(rows), 'request_status':'finished', 'reply_status':'replied'}))
        return events

    def execute(self, sid, body, make_machine, request_id=None):
        with self.lock:
            request,old=self.start(sid,body,request_id)
            if old:return self.replay(sid,request,old)
            control = RequestControl(request)
            self.controls[sid, request] = control
        try:
            kind='user' if 'content' in body else 'decision'
            shown={'content':body['content']} if kind=='user' else {k:v for k,v in body.items() if k in {'check_id','decision','plan_id','action','step_ref','reason'}}
            # Persist admission before the first generator advance: disconnects
            # during setup must not erase the user's interrupted instruction.
            self.append(sid,kind,shown,request,request+':input')
            machine=make_machine(request)
            machine.control = control
            machine.request_id = request
            if hasattr(machine.tools, 'request_id'):
                machine.tools.control = control
            # Request-id duplicate lookup above precedes AgentStore.preflight.
            events=machine.message(**body)
        except BaseException:
            self.finish(sid,request,'failed',False)
            with self.lock:self.controls.pop((sid, request), None)
            raise
        def stream():
            complete=False;failed=False
            try:
                control.check()
                for index,(event,payload) in enumerate(events):
                    if event not in EVENTS:raise _failure('SESSION_EVENT_INVALID','未知显示事件')
                    if event != 'progress':
                        self.append(sid,event,payload,request,request+':'+str(index))
                    failed=failed or event=='error'
                    yield event,payload
                complete=True
            except RequestCancelled:
                payload = {'code': 'REQUEST_INTERRUPTED', 'detail': '请求已停止；已完成操作保留，后台任务请在任务卡片中单独核对。'}
                self.append(sid,'error',payload,request,request+':cancelled')
                yield 'error',payload
            finally:
                events.close()
                self.finish(sid,request,'failed' if failed else 'completed' if complete else 'interrupted',complete)
                with self.lock:self.controls.pop((sid, request), None)
        iterator=stream()
        outer=self
        class LeasedStream:
            started=False
            closed=False
            next_lock=RLock()
            def __iter__(self):return self
            def __next__(self):
                with self.next_lock:
                    if self.closed:raise StopIteration
                    self.started=True
                    try:return next(iterator)
                    finally:
                        if self.closed:iterator.close()
            def close(self):
                if self.closed:return
                self.closed=True
                control.cancel()
                # A disconnect may arrive while next() waits on HTTP or a tool.
                # The worker closes itself after recording the operation result.
                if not self.next_lock.acquire(blocking=False):return
                try:
                    iterator.close()
                    if not self.started:
                        events.close()
                        outer.finish(sid,request,'interrupted',False)
                        with outer.lock:outer.controls.pop((sid, request), None)
                finally:self.next_lock.release()
        return LeasedStream()
