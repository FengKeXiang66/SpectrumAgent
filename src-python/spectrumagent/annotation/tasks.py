"""Run-scoped, bounded annotation preparation queue with owned progress views."""
from collections import deque
from copy import deepcopy
from hashlib import sha256
import json
from threading import RLock, Thread, Event, current_thread
from time import monotonic
from uuid import uuid4

from spectrumagent.data import DataError
from spectrumagent.agent.authorization import source_baseline, task_target_hash


TERMINAL = {'completed', 'canceled', 'failed'}
STATUSES = ('pending', 'processing', 'ready', 'failed', 'conflict', 'not_attempted')


def failure(code, detail):
    error = DataError(code, detail)
    error.status_code = 409
    return error


class AnnotationTasks:
    """No worker survives an idle queue; metadata lives only in this engine."""
    def __init__(self, batch, boot_id, *, capacity=32, terminal_limit=32):
        self.batch, self.boot_id, self.capacity = batch, boot_id, capacity
        self.terminal_limit = terminal_limit
        self.lock = RLock()
        self.queue, self.receipts, self.requests = deque(), {}, {}
        self.worker = None
        self.expired = set()

    def _owned(self, sid, task_id):
        task = self.receipts.get(task_id)
        if (sid, task_id) in self.expired:
            raise failure('TASK_EXPIRED', '任务明细已过期，不会自动重新执行')
        if not task or task['owner_session_id'] != sid or task['owner_boot_id'] != self.boot_id:
            raise failure('TASK_NOT_FOUND', '任务不存在、已过期或不属于本会话')
        return task

    def submit(self, sid, request_id, cube_ids, grant, *, slot=0, retry_of=None, retry_mode='failed'):
        ids = list(cube_ids)
        if not ids or len(set(ids)) != len(ids):
            raise failure('INVALID_REQUEST', '任务范围必须非空且不重复')
        body = {'cube_ids': sorted(ids), 'profile': 'annotation-default-v1', 'retry_of': retry_of, 'retry_mode': retry_mode}
        fingerprint = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        key = (sid, self.boot_id, request_id, slot)
        with self.lock:
            if key in self.requests:
                old_hash, task_id = self.requests[key]
                if old_hash != fingerprint:
                    raise failure('IDEMPOTENCY_CONFLICT', '请求 ID 已用于另一准备任务')
                return self.accepted(self._owned(sid, task_id))
            if (grant.get('session_id') != sid or grant.get('boot_id') != self.boot_id
                    or 'prepare' not in grant.get('operations', []) or not set(ids).issubset(grant.get('cube_ids', []))):
                raise failure('OPERATION_NOT_AUTHORIZED', '任务超出准备分割的授权范围')
            if self._queued_count() >= self.capacity:
                raise failure('BUSY', '准备队列已满，请稍后重试')
            baselines = {cube: deepcopy(grant['baselines'][cube]) for cube in ids}
            task_id = str(uuid4())
            names = self.batch.registry.display_names()
            task = {'task_id': task_id, 'owner_session_id': sid, 'owner_boot_id': self.boot_id,
                    'task_status': 'queued', 'phase': 'verifying', 'result_status': None,
                    'snapshot_version': 1, 'cancel_requested': False, 'current_cube_id': None,
                    'task_target_id': None, 'authorization_id': grant['authorization_id'],
                    'grant': grant,
                    'members': [{'cube_id': c} for c in ids], 'baselines': baselines,
                    'expected_content_hashes': deepcopy(grant.get('expected_content_hashes', {})),
                    'items': [{'cube_id': c, 'display_name': names.get(c, '缺失样品'),
                               'status': 'pending', 'action': 'none', 'superpixel_count': None,
                               'error_code': None, 'detail': None} for c in ids],
                    'retry_of': retry_of, 'started': monotonic(), 'error': None}
            self.receipts[task_id] = task
            self.requests[key] = fingerprint, task_id
            self.queue.append(task_id)
            if self.worker is None:
                self.worker = Thread(target=self._run, daemon=True, name='annotation-preparation')
                self.worker.start()
            return self.accepted(task)

    def _queued_count(self):
        return sum(isinstance(entry, dict) or self.receipts[entry]['task_status'] == 'queued' for entry in self.queue)

    def run_sync(self, operation):
        """Legacy single-image/custom-parameter endpoints share the same bounded worker."""
        if current_thread() is self.worker:
            return operation()
        from spectrumagent.projects import worker
        entry = {'operation': worker(operation), 'done': Event()}
        with self.lock:
            if self._queued_count() >= self.capacity:
                raise failure('BUSY', '准备队列已满，请稍后重试')
            self.queue.append(entry)
            if self.worker is None:
                self.worker = Thread(target=self._run, daemon=True, name='annotation-preparation')
                self.worker.start()
        entry['done'].wait()
        if 'error' in entry:
            raise entry['error']
        return entry['result']

    @staticmethod
    def accepted(task):
        return {'status': 'accepted', 'task_id': task['task_id'], 'task_status': task['task_status'],
                'member_count': len(task['members'])}

    def _change(self, task, **changes):
        task.update(changes)
        task['snapshot_version'] += 1

    def _item(self, task, index, **changes):
        task['items'][index] = {**task['items'][index], **changes}
        task['snapshot_version'] += 1

    def _finish(self, task, status, error=None):
        for i, row in enumerate(task['items']):
            if row['status'] in {'pending', 'processing'}:
                self._item(task, i, status='not_attempted', error_code='CANCELED' if status == 'canceled' else 'TASK_STOPPED')
        ready = sum(row['status'] == 'ready' for row in task['items'])
        result = 'all_ready' if ready == len(task['items']) else 'partial' if ready else 'failed'
        self._change(task, task_status=status, current_cube_id=None, result_status=result, error=error)
        task['finished'] = monotonic()
        self._collect()

    def _collect(self):
        terminal = sorted((t for t in self.receipts.values() if t['task_status'] in TERMINAL),
                          key=lambda t: t['finished'])
        for task in terminal[:-self.terminal_limit]:
            if task.get('read_until', 0) >= monotonic() or task['task_id'] in self.queue:
                continue
            self.expired.add((task['owner_session_id'], task['task_id']))
            self.receipts.pop(task['task_id'])

    def _run(self):
        while True:
            with self.lock:
                if not self.queue:
                    self.worker = None
                    return
                entry = self.queue.popleft()
                if isinstance(entry, str):
                    task = self.receipts[entry]
                    if task['task_status'] in TERMINAL:
                        continue
                    self._change(task, task_status='running')
            if isinstance(entry, dict):
                try:
                    entry['result'] = entry['operation']()
                except BaseException as error:
                    entry['error'] = error
                finally:
                    entry['done'].set()
                continue
            try:
                self._execute(task)
            except BaseException as error:
                with self.lock:
                    self._finish(task, 'failed', getattr(error, 'code', 'PREPARE_FAILED'))

    def _execute(self, task):
        from spectrumagent.projects import bind, session_project
        with bind(session_project(self.batch.registry.database, task['owner_session_id'])):
            return self._execute_project(task)

    def _execute_project(self, task):
        verified = []
        for index, member in enumerate(task['members']):
            cube = member['cube_id']
            with self.lock:
                if task['cancel_requested']:
                    self._finish(task, 'canceled'); return
                if 'prepare' not in task['grant']['operations']:
                    self._finish(task, 'failed', 'AUTHORIZATION_REVOKED'); return
                self._change(task, current_cube_id=cube)
                self._item(task, index, status='processing')
            try:
                if task['baselines'][cube] is None:
                    raise failure('MEMBER_UNAVAILABLE', '授权时源数据不可用，请明确发起新任务')
                baseline = tuple(tuple(p) for p in task['baselines'][cube])
                if source_baseline(self.batch.registry, cube) != baseline:
                    raise failure('SOURCE_CHANGED', '源身份已变化')
                identity, signature = self.batch.engine.source_identity(cube)
                if signature != baseline:
                    raise failure('SOURCE_CHANGED', '源身份已变化')
                if task['expected_content_hashes'].get(cube, identity) != identity:
                    raise failure('CONTENT_MISMATCH', '当前内容与明确版本不同')
                verified.append((index, {'cube_id': cube, 'content_hash': identity}))
                with self.lock:
                    task['members'][index] = {'cube_id': cube, 'content_hash': identity}
                    task['grant']['expected_content_hashes'][cube] = identity
                    self._item(task, index, status='pending')
            except Exception as error:
                with self.lock:
                    self._item(task, index, status='failed', error_code=getattr(error, 'code', 'MEMBER_UNAVAILABLE'),
                               detail='源数据核验失败，未生成分割。')
        with self.lock:
            if verified:
                self._change(task, task_target_id=task_target_hash((m['cube_id'], m['content_hash']) for _, m in verified), phase='preparing')
                task['grant']['verified_targets'][task['task_target_id']] = [m['cube_id'] for _,m in verified]
                task['grant']['status'] = 'active'
        for index, member in verified:
            with self.lock:
                if task['cancel_requested']:
                    self._finish(task, 'canceled'); return
                if 'prepare' not in task['grant']['operations']:
                    self._finish(task, 'failed', 'AUTHORIZATION_REVOKED'); return
                self._change(task, current_cube_id=member['cube_id'])
                self._item(task, index, status='processing')
            try:
                result = self.batch._prepare_item(member, task['items'][index]['display_name'])
            except Exception as error:
                if not isinstance(error, DataError):
                    import logging
                    logging.getLogger(__name__).exception('Annotation preparation failed')
                result = self.batch._item(member['cube_id'], task['items'][index]['display_name'], 'failed',
                                          code=getattr(error, 'code', 'PREPARE_FAILED'))
            with self.lock:
                self._item(task, index, **result)
        with self.lock:
            self._finish(task, 'canceled' if task['cancel_requested'] else 'completed')

    def context(self, sid):
        """Small, owned, scalar summaries for model context; no item geometry."""
        with self.lock:
            owned = [task for task in self.receipts.values() if task['owner_session_id'] == sid]
            result = []
            for task in owned[-20:]:
                summary = {key: task[key] for key in ('task_id', 'task_status', 'phase', 'result_status', 'cancel_requested')}
                summary['total'] = len(task['items'])
                summary.update({status + '_count': sum(item['status'] == status for item in task['items']) for status in STATUSES})
                result.append(summary)
            return result

    def view(self, sid, task_id, *, after=None, limit=50, version=None):
        with self.lock:
            task = self._owned(sid, task_id)
            task['read_until'] = monotonic() + 30  # Active polling protects terminal detail; no permanent pin.
            counts = {status: sum(i['status'] == status for i in task['items']) for status in STATUSES}
            result = {k: task[k] for k in ('task_id', 'task_status', 'phase', 'result_status', 'snapshot_version',
                      'cancel_requested', 'current_cube_id', 'task_target_id', 'authorization_id', 'retry_of', 'error')}
            result.update(total=len(task['items']), counts=counts, cancelable=task['task_status'] not in TERMINAL,
                          owner_boot_id=self.boot_id, session_id=sid)
            if after is not None:
                if not 1 <= limit <= 100 or after < 0:
                    raise failure('INVALID_REQUEST', '分页参数无效')
                if version is not None and version != task['snapshot_version']:
                    raise failure('TASK_SNAPSHOT_CHANGED', '任务状态已更新，请刷新分页')
                result['items'] = deepcopy(task['items'][after:after+limit])
                result['next_after'] = after+limit if after+limit < len(task['items']) else None
            return result

    def cancel(self, sid, task_id):
        with self.lock:
            task = self._owned(sid, task_id)
            if task['task_status'] not in TERMINAL:
                self._change(task, cancel_requested=True)
                if task['task_status'] == 'queued':
                    self._finish(task, 'canceled')
            return self.view(sid, task_id)

    def retry(self, sid, task_id, request_id, grant, mode='failed'):
        with self.lock:
            parent = self._owned(sid, task_id)
            if parent['task_status'] not in TERMINAL:
                raise failure('TASK_RUNNING', '请等待父任务结束后重试')
            statuses = {'failed'} if mode == 'failed' else {'not_attempted'} if mode == 'remaining' else set()
            if not statuses:
                raise failure('INVALID_REQUEST', '重试模式无效')
            ids = [r['cube_id'] for r in parent['items'] if r['status'] in statuses]
            if not ids:
                raise failure('NOTHING_TO_RETRY', '没有匹配的未完成项')
            # Preserve the original baseline, even if a later command granted a
            # different source identity. A changed source needs a new task.
            for cube in ids:
                current_baseline = grant.get('baselines', {}).get(cube)
                original_baseline = parent['baselines'][cube]
                if current_baseline is None or original_baseline is None or tuple(map(tuple,current_baseline)) != tuple(map(tuple,original_baseline)):
                    raise failure('SOURCE_CHANGED', '源身份已变化，请明确发起新任务')
            return self.submit(sid, request_id, ids, grant, retry_of=task_id, retry_mode=mode)
