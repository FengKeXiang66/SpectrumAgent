"""Synchronous batch annotation preparation; no persisted batch jobs.

2026-11-13 ruling: an explicit cube scope no longer requires a frozen dataset
version. Version determination and freezing belong to the step before modeling.
Both entry points snapshot source content identity at batch start. Batch size
has no static ceiling; runtime memory is enforced per item, so a large scope
degrades into isolated item failures instead of a whole-batch veto.
The application owns this service for exactly its engine/session lifetime.
"""
from collections import OrderedDict, deque
from dataclasses import asdict
from pathlib import Path
from threading import Lock
from time import monotonic
from uuid import uuid4
import ctypes
import sys

import numpy as np

from spectrumagent.data import DataError
from spectrumagent.dataset_version.store import batch_content_hash
from .engines.superpixels import Parameters, algorithm_version, memory_bytes

# Retained for the per-item memory policy and historical capacity tests. The
# aggregate ceilings below are no longer applied as a whole-batch veto.
MAX_MEMBERS = 5
MAX_LINES, MAX_SAMPLES, MAX_BANDS = 231, 640, 200
MAX_ITEM_SOURCE_BYTES = 59138585
MAX_TOTAL_SOURCE_BYTES = 295692925
MAX_TOTAL_PIXELS = 739200
MAX_RETAINED_BYTES = 128 * 1024 * 1024
MAX_RSS_FRACTION = .5
TIME_BUDGET_SECONDS = 180  # No longer stops a batch; kept for per-item error text.
MAX_COMPLETED_RECEIPTS = 32
PROFILE = 'annotation-default-v1'


def retained_bytes(engine, sessions):
    """Count live cache/state arrays and metadata once, including existing cubes."""
    if getattr(engine, 'resources', None) is not None:
        return engine.resources.retained_bytes()
    seen = set()
    def size(value):
        if id(value) in seen:
            return 0
        seen.add(id(value))
        if isinstance(value, np.ndarray):
            return value.nbytes
        if isinstance(value, dict):
            return sys.getsizeof(value) + sum(size(k) + size(v) for k, v in value.items())
        if isinstance(value, (tuple, list, deque, set, frozenset)):
            return sys.getsizeof(value) + sum(size(v) for v in value)
        if hasattr(value, '__dict__'):
            return sys.getsizeof(value) + size(vars(value))
        return sys.getsizeof(value)
    return size(engine.cache) + size(sessions._states) + size(getattr(sessions, '_orchestration_previews', {}))


def physical_memory_bytes():
    class Status(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page', 'available_page',
                                                  'virtual', 'available_virtual', 'extended')]
    status = Status()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise DataError('BATCH_MEMORY_UNAVAILABLE', '无法核验内存预算，未开始准备')
    return status.total


class BatchPrepareService:
    def __init__(self, versions, engine, sessions, *, clock=monotonic):
        self.versions, self.engine, self.sessions = versions, engine, sessions
        self.registry = engine.registry
        self.clock = clock
        self._execution_lock = Lock()  # Only batch requests serialize; engine lock is per item.
        self.receipts = OrderedDict()
        if self.engine.resources is not None:self.engine.resources._batches.add(self)

    def _base(self, version, started, count=0, requested=0, retry_of=None):
        return {'status': 'blocked', 'batch_ref': None, 'retry_of': retry_of,
                'dataset_version_id': version, 'scope_key': None, 'member_count': count, 'requested_count': requested,
                'ready_count': 0, 'failed_count': 0, 'conflict_count': 0, 'not_attempted_count': count,
                'profile': PROFILE, **asdict(Parameters()), 'algorithm_version': algorithm_version(),
                'auto_open': False, 'open_cube_id': None, 'elapsed_ms': int((self.clock()-started)*1000),
                'truncated': False}

    @staticmethod
    def _item(cube, name, status, *, action='none', count=None, code=None):
        details = {
            'SOURCE_CHANGED': '源文件内容已变化，请核查该样品与本次范围快照。',
            'CONTENT_MISMATCH': '当前内容与本次范围快照不一致，未附接分割。',
            'MEMBER_UNAVAILABLE': '样品已回收、删除或源文件不可读。',
            'SEGMENTATION_CONFLICT': '已有不同参数或人工依赖，请在单图工作台核查后重试。',
            'READY_INVALIDATED': '原成功项已失效；本次仅核验，未重新计算。',
            'BATCH_TIME_BUDGET': '已达到同步时间预算，本项尚未执行。',
            'BATCH_MEMORY_BUDGET': '已达到内存预算，本项尚未执行。',
            'PREPARE_FAILED': '该样品准备失败，请核查后仅重试未就绪项。',
            'CACHE_MEMORY_BUDGET': '资源预算不足，本项未提交；像素标注与历史保留。',
            'CACHE_DISK_BUDGET': '磁盘缓存预算不足，本项未提交持久分割。',
            'CACHE_UNAVAILABLE': '分割存储暂不可用，未更改原标注。',
            'SEGMENTATION_CORRUPT': '分割产物损坏，请核查后显式重新准备。',
            'SEGMENTATION_INCOMPATIBLE': '分割格式或算法不兼容，未自动重算。',
            'SEGMENTATION_STALE': '分割与源或工作态不一致，未自动重算。',
        }
        detail = details.get(code)
        if code == 'BATCH_MEMORY_BUDGET' and status == 'failed':
            detail = '准备结果超过内存预算，未附接工作态。'
        return {'cube_id': cube, 'display_name': name, 'status': status, 'action': action,
                'superpixel_count': count, 'error_code': code, 'detail': detail}

    def _admit(self, members, diagnostics=None):
        from .prepare_admission import scan, blocked
        policy = sys.modules[__name__]
        decision = scan(members, self.registry, policy, resources=self.engine.resources, execution=True)
        if diagnostics is not None: diagnostics.update(decision.fields())
        if decision.assessment == 'blocked':
            return 'BATCH_MEMBERS_UNAVAILABLE'
        # Per-item ceiling only: a large scope must never be vetoed as a whole.
        if self.engine.resources is not None:
            try:
                self.engine.resources.ensure(decision.largest_reservation)
            except DataError:
                if diagnostics is not None:
                    diagnostics.update(blocked('RUNTIME_MEMORY_LIMIT', 'runtime_memory_budget', None, MAX_RETAINED_BYTES,
                        '单个样品的内存准入未通过，本次未开始处理。').fields())
                return 'BATCH_MEMORY_BUDGET'
            return None
        if memory_bytes()[0] > physical_memory_bytes() * MAX_RSS_FRACTION:
            if diagnostics is not None:
                diagnostics.update(blocked('RUNTIME_MEMORY_LIMIT', 'runtime_memory_budget', None, MAX_RETAINED_BYTES,
                    '当前内存占用过高，本次未开始处理。').fields())
            return 'BATCH_MEMORY_BUDGET'
        return None

    def _dependent(self, cube, state):
        if state is not None and (state.candidates or state.gestures or state.undo_stack
                                   or state.revision or (state.label_map is not None and np.any(state.label_map != -1))):
            return True
        if any(item['cube_id'] == cube for item in getattr(self.sessions, '_orchestration_previews', {}).values()):
            return True
        draft = self.sessions.drafts.get(cube)
        return bool(draft and (draft['revision'] or draft['document'].get('regions')))

    @staticmethod
    def _state_matches(state, result, params):
        return (state is not None and state.segments is not None and state.params is not None
                and all(state.params.get(k) == v for k, v in asdict(params).items())
                and state.segmentation_content_hash == result.content_hash
                and state.segmentation_algorithm_version == result.algorithm_version
                and np.array_equal(state.segments, result.segments))

    def _prepare_item(self, member, name, *, retained=False):
        if self.engine.resources is not None:
            return self._managed_item(member, name, retained=retained)
        cube, expected = member['cube_id'], member['content_hash']
        with self.engine.lock, self.sessions._lock:
            identity, signature = self.engine.source_identity(cube)
            if identity != expected:
                return self._item(cube, name, 'failed', code='CONTENT_MISMATCH')
            cached = self.engine.cache.get(cube)
            state = self.sessions._states.get(cube)
            params = Parameters()
            valid = bool(cached and getattr(cached[1], 'content_hash', None) == identity
                         and getattr(cached[1], 'algorithm_version', None) == algorithm_version())
            matches = valid and cached[0] == params and self._state_matches(state, cached[1], params)
            if retained:
                if not matches:
                    return self._item(cube, name, 'failed', code='READY_INVALIDATED')
                if self.engine.source_identity(cube) != (identity, signature):
                    return self._item(cube, name, 'failed', code='SOURCE_CHANGED')
                return self._item(cube, name, 'ready', action='retained', count=int(cached[1].report['superpixel_count']))
            state_valid = bool(state is not None and state.params is not None
                               and state.segmentation_content_hash == identity
                               and state.segmentation_algorithm_version == algorithm_version())
            different = ((valid and cached[0] != params)
                         or (state_valid and any(state.params.get(k) != v for k, v in asdict(params).items())))
            if different or (not matches and self._dependent(cube, state)):
                return self._item(cube, name, 'conflict', code='SEGMENTATION_CONFLICT')
            if matches:
                if self.engine.source_identity(cube) != (identity, signature):
                    return self._item(cube, name, 'failed', code='SOURCE_CHANGED')
                return self._item(cube, name, 'ready', action='reused', count=int(cached[1].report['superpixel_count']))
            previous = cached
            result = self.engine.generate(cube, params, force=not valid)
            try:
                if self.engine.source_identity(cube) != (identity, signature):
                    raise DataError('SOURCE_CHANGED', '源文件在准备期间变化')
                # Account for the state copies BEFORE attachment, including a
                # newly allocated label map. Checking the engine cache alone
                # leaves a gap at the exact retained-memory boundary.
                attachment_bytes = result.segments.nbytes + 4096
                if state is None:
                    attachment_bytes += result.segments.size * np.dtype('int32').itemsize
                elif state.segments is not None:
                    attachment_bytes -= state.segments.nbytes
                if (retained_bytes(self.engine, self.sessions) + max(0, attachment_bytes) > MAX_RETAINED_BYTES
                        or memory_bytes()[0] > physical_memory_bytes() * MAX_RSS_FRACTION):
                    raise DataError('BATCH_MEMORY_BUDGET', '准备结果超过内存预算')
                self.sessions.set_segmentation(cube, result)
            except BaseException:
                if previous is None:
                    self.engine.cache.pop(cube, None)
                else:
                    self.engine.cache[cube] = previous
                raise
            return self._item(cube, name, 'ready', action='reused' if valid else 'generated',
                              count=int(result.report['superpixel_count']))

    def _managed_item(self, member, name, *, retained=False):
        cube, expected = member['cube_id'], member['content_hash']
        r = self.engine.resources
        with r.lease(cube, required=False, restore=False):
            identity, _ = self.engine.source_identity(cube)
            if identity != expected:return self._item(cube,name,'failed',code='CONTENT_MISMATCH')
            info = r.store.inspect(cube,content_hash=identity)
            params = Parameters();cached = self.engine.cache.get(cube);state = self.sessions._states.get(cube)
            valid = bool(cached and cached[1].content_hash==identity and cached[1].algorithm_version==algorithm_version())
            matches = valid and cached[0]==params and self._state_matches(state,cached[1],params)
            different = ((info is not None and info['params']!=params) or (valid and cached[0]!=params)
                         or (state is not None and state.params is not None and state.segmentation_content_hash==identity
                             and any(state.params.get(k)!=v for k,v in asdict(params).items())))
            if retained:
                if info is None or different:return self._item(cube,name,'failed',code='READY_INVALIDATED')
                result,_,_=r.read(cube)
                if result is None:return self._item(cube,name,'failed',code='READY_INVALIDATED')
                return self._item(cube,name,'ready',action='retained',count=int(result.report['superpixel_count']))
            if different or (self._dependent(cube,state) and (
                    (cached is not None and not matches)
                    or (state is not None and state.segments is not None and not state.segmentation_ref))):
                return self._item(cube,name,'conflict',code='SEGMENTATION_CONFLICT')
            result,action=r.prepare(cube,params)
            return self._item(cube,name,'ready',action=action,count=int(result.report['superpixel_count']))

    def _snapshot(self, cube_ids):
        """Snapshot source identity for an explicit scope; no version row is written."""
        if not cube_ids or len(set(cube_ids)) != len(cube_ids):
            raise DataError('INVALID_REQUEST', '批量范围须为非空且不重复的数据集引用')
        return [{'cube_id': cube, 'content_hash': self.engine.source_identity(cube)[0]}
                for cube in cube_ids]

    def prepare(self, dataset_version_id=None, retry_of=None, *, cube_ids=None):
        """Two entries: an explicit cube scope, or a legacy frozen version.

        The scope path never persists or freezes a version: version determination
        belongs to the step before modeling (2026-11-13 ruling).
        """
        started = self.clock()
        with self._execution_lock:
            parent = self.receipts.get(retry_of) if retry_of else None
            if retry_of and parent is None:
                return {**self._base(None, started, retry_of=retry_of),
                        'error_code': 'BATCH_REF_EXPIRED', 'detail': '回执已失效，请核查范围后明确发起新的批次。'}
            if parent is not None and not cube_ids and dataset_version_id is None:
                # A retry keeps the exact scope of its parent receipt.
                members, version = parent['members'], parent['dataset_version_id']
            elif dataset_version_id is not None:
                try:
                    frozen = self.versions.get_frozen(dataset_version_id)
                except (DataError, OSError, ValueError):
                    return {**self._base(str(dataset_version_id), started, retry_of=retry_of),
                            'error_code': 'DATASET_VERSION_INVALID', 'detail': '版本不存在、未冻结或成员记录不完整。'}
                members, version = frozen['members'], frozen['id']
            elif cube_ids:
                try:
                    members = self._snapshot(cube_ids)
                except DataError as error:
                    return {**self._base(None, started, retry_of=retry_of),
                            'error_code': error.code, 'detail': error.payload.detail}
                version = None
            else:
                return {**self._base(None, started, retry_of=retry_of),
                        'status': 'need_scope', 'missing': 'cube_ids'}
            scope_key = batch_content_hash(member['content_hash'] for member in members)
            base = self._base(version, started, len(members), retry_of=retry_of)
            base['scope_key'] = scope_key
            if parent is not None:
                if parent.get('dataset_version_id') != version:
                    return {**base, 'error_code': 'BATCH_VERSION_MISMATCH', 'detail': '重试版本与父回执不同，未执行。'}
                if parent.get('scope_key') not in (None, scope_key):
                    return {**base, 'error_code': 'BATCH_SCOPE_MISMATCH', 'detail': '重试范围与父回执不同，未执行。'}
            with self.engine.lock, self.sessions._lock:
                diagnostics = {}
                reason = self._admit(members, diagnostics)
            if reason:
                return {**base, 'error_code': reason, 'detail': diagnostics['detail'],
                        **{f'admission_{key}': diagnostics[value] for key, value in {
                            'reason':'check_code', 'constraint':'constraint', 'actual':'actual',
                            'limit':'limit', 'checked_at':'checked_at'}.items()}}
            names = self.registry.display_names()
            targets = {item['cube_id'] for item in parent['items'] if item['status'] != 'ready'} if parent else {m['cube_id'] for m in members}
            reference = 'b-' + uuid4().hex
            receipt = {'dataset_version_id': version, 'scope_key': scope_key, 'members': members,
                       'items': [], 'params': asdict(Parameters()),
                       'algorithm_version': algorithm_version(), 'completed': False}
            self.receipts[reference] = receipt
            stop_code = None
            for member in members:
                cube = member['cube_id']
                name = names.get(cube, '不可用样品')
                if stop_code:
                    # Previous successes still require verification on retries.
                    if cube in targets:
                        receipt['items'].append(self._item(cube, name, 'not_attempted', code=stop_code))
                        continue
                try:
                    item = self._prepare_item(member, name, retained=cube not in targets)
                except Exception as error:
                    code = getattr(error, 'code', '')
                    code = code if code in {'SOURCE_CHANGED', 'BATCH_MEMORY_BUDGET','CACHE_MEMORY_BUDGET','CACHE_DISK_BUDGET',
                                           'CACHE_UNAVAILABLE','SEGMENTATION_CORRUPT','SEGMENTATION_INCOMPATIBLE','SEGMENTATION_STALE'} else (
                        'MEMBER_UNAVAILABLE' if code == 'DATASET_NOT_FOUND' or isinstance(error, OSError) else 'PREPARE_FAILED')
                    item = self._item(cube, name, 'failed', code=code)
                    if code in {'BATCH_MEMORY_BUDGET','CACHE_MEMORY_BUDGET'}:
                        stop_code = code
                receipt['items'].append(item)
            receipt['completed'] = True
            self.receipts.move_to_end(reference)  # Completion order, not access order.
            finished = [ref for ref, r in self.receipts.items() if r['completed']]
            for ref in finished[:-MAX_COMPLETED_RECEIPTS]:
                del self.receipts[ref]
            counts = {status: sum(item['status'] == status for item in receipt['items'])
                      for status in ('ready', 'failed', 'conflict', 'not_attempted')}
            ready = [item for item in receipt['items'] if item['status'] == 'ready']
            status = 'ready' if counts['ready'] == len(members) else 'partial' if ready else 'failed'
            summary = {**base, 'batch_ref': reference, 'requested_count': len(targets), 'status': status,
                       **{key+'_count': value for key, value in counts.items()},
                       'auto_open': status == 'ready', 'open_cube_id': ready[0]['cube_id'] if ready else None,
                       'elapsed_ms': int((self.clock()-started)*1000)}
            for i, item in enumerate(receipt['items'], 1):
                summary.update({f'item_{i}_{k}': v for k, v in item.items()})
            return summary
