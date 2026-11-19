"""Application-owned durable segmentation resources and short-lived leases.

Lock graph: deletion coordinator job -> engine.lock -> sessions._lock -> store.lock.
The last lock only owns disk quota/pin metadata, and never calls the engine or
sessions. All memory accounting/reservations use the first two reentrant locks.
An operation leases its cube; visible canvases hold a separate, releasable pin.
"""
from collections import OrderedDict, deque
from contextlib import contextmanager
from copy import copy
from dataclasses import asdict
from functools import wraps
import sys
from time import perf_counter
from weakref import WeakSet

import numpy as np

from spectrumagent.data import DataError
from .engines.superpixels import ALGORITHM_VERSION, Parameters, memory_bytes
from .segmentation_store import SegmentationStore, fail

RETAINED_LIMIT = 128 * 1024**2
RSS_FRACTION = .5


def unique_bytes(*objects):
    """Object metadata plus underlying ndarray allocations, including views."""
    seen=set();spans=[]
    def size(obj):
        if id(obj) in seen:return 0
        seen.add(id(obj))
        if isinstance(obj,np.ndarray):
            root=obj
            while isinstance(root.base,np.ndarray):root=root.base
            if root.size:
                pointer=root.__array_interface__['data'][0]
                spans.append((pointer,pointer+root.nbytes))
            return max(0,sys.getsizeof(obj)-(obj.nbytes if obj.flags.owndata else 0))
        if isinstance(obj,dict):return sys.getsizeof(obj)+sum(size(k)+size(v) for k,v in obj.items())
        if isinstance(obj,(list,tuple,deque,set,frozenset)):return sys.getsizeof(obj)+sum(size(v) for v in obj)
        if hasattr(obj,'__dict__'):return sys.getsizeof(obj)+size(vars(obj))
        return sys.getsizeof(obj)
    metadata=sum(size(o) for o in objects);total=0;end=0
    for a,b in sorted(spans):
        total+=max(0,b-max(a,end));end=max(end,b)
    return metadata+total


def budget_error():
    e=DataError('CACHE_MEMORY_BUDGET','分割或编辑资源预算不足，原标注与历史保持不变');e.status_code=409;return e


def managed(*,required=False,restore=True):
    """Acquire in engine->session order BEFORE the legacy method takes its lock."""
    def decorate(method):
        @wraps(method)
        def run(self,cube_id,*args,**kwargs):
            if self.resources is None:return method(self,cube_id,*args,**kwargs)
            with self.resources.lease(cube_id,required=required,restore=restore):
                return method(self,cube_id,*args,**kwargs)
        return run
    return decorate


class SegmentationResources:
    def __init__(self,paths,engine,sessions,*,retained_limit=RETAINED_LIMIT,store=None):
        self.engine,self.sessions=engine,sessions
        self.store=store or SegmentationStore(paths)
        self.retained_limit=retained_limit
        self._pins={};self._lru=OrderedDict();self._canvas_focus={}
        self._temporary=0;self.peak_temporary_bytes=0
        self.failed=set()
        self._batches=WeakSet()
        engine.resources=self;sessions.resources=self;engine.registry.segmentation_resources=self

    def retained_bytes(self):
        return unique_bytes(self.engine.cache,self.sessions._states,getattr(self.sessions,'_orchestration_previews',{}),
                            self._pins,self._lru,self.failed,self.store.access,self.store.pins,[s.receipts for s in self._batches])

    @staticmethod
    def expected_bytes(shape,params=Parameters()):
        h,w,b=shape
        return h*w*(24+params.pca_components*8+(20 if params.pca_components!=5 else 0))+min(h*w,params.n_segments*4)*b*16+65536

    def _touch(self,cube):
        self._lru.pop(cube,None);self._lru[cube]=None

    def _evict(self,cube):
        cached=self.engine.cache.get(cube)
        state=self.sessions._states.get(cube)
        ref=getattr(cached[1],'segmentation_ref',None) if cached else getattr(state,'segmentation_ref',None)
        if self._pins.get(cube) or cube in self._canvas_focus.values():return False
        if not ref:
            if cached is None and state is not None and state.segments is None and state.label_map is not None:
                state.label_map=None;self._lru.pop(cube,None);return True
            return False
        # Do not discard the only copy. Integrity is rechecked on every reload.
        try:
            if self.store.active(cube)!=ref or self.store.inspect(cube,ref=ref) is None:return False
        except (DataError,OSError):return False
        self.engine.cache.pop(cube,None)
        if state is not None:
            state.segments=None
            state.label_map=None # reconstructible from unchanged authoritative draft
        self._lru.pop(cube,None)
        return True

    def canvas_focus(self, owner, cube, *, release=False):
        """Short metadata update; never hold an engine lease for an open canvas."""
        with self.engine.lock, self.sessions._lock:
            if release:
                if self._canvas_focus.get(owner) == str(cube):
                    self._canvas_focus.pop(owner, None)
            else:
                self.engine.registry.get(cube)
                self._canvas_focus[owner] = str(cube)

    def ensure(self,amount=0,*,cube=None):
        """Reserve before allocation/CAS; caller holds engine then session locks."""
        if cube in self.failed:raise fail('CACHE_UNAVAILABLE')
        if amount<0 or amount>self.retained_limit:raise budget_error()
        for candidate in list(self._lru):
            if self.retained_bytes()+amount<=self.retained_limit:break
            if candidate!=cube:self._evict(candidate)
        if self.retained_bytes()+amount>self.retained_limit:raise budget_error()

    @contextmanager
    def temporary(self,amount):
        from .prepare_batch import physical_memory_bytes
        if amount<0 or memory_bytes()[0]+self._temporary+amount>physical_memory_bytes()*RSS_FRACTION:raise budget_error()
        self._temporary+=amount;self.peak_temporary_bytes=max(self.peak_temporary_bytes,self._temporary)
        try:yield
        finally:self._temporary-=amount

    @contextmanager
    def lease(self,cube,*,required=True,restore=True):
        cube=str(cube)
        with self.engine.registry.recycle.coordinator.job(),self.engine.lock,self.sessions._lock:
            dataset,_=self.engine.registry.get(cube)
            if cube in self.failed:raise fail('CACHE_UNAVAILABLE')
            nested = self._pins.get(cube,0)>0
            self._pins[cube]=self._pins.get(cube,0)+1
            ref=None;workspace=None;workspace_entered=False
            try:
                if not nested:
                    workspace=self.temporary(int(np.prod(dataset.shape))*32+int(np.prod(dataset.shape[:2]))*128+8*1024**2)
                    workspace.__enter__();workspace_entered=True
                cached=(self.engine.cache.get(cube) or (None,None))[1]
                result=self._read(cube)[0] if restore and not (nested and cached is not None) else cached
                if required and result is None:raise DataError('SUPERPIXELS_REQUIRED','请先显式准备超像素分割')
                if result is not None:
                    ref=getattr(result,'segmentation_ref',None)
                    if ref:
                        with self.store.lock:self.store.pins[(cube,ref)]=self.store.pins.get((cube,ref),0)+1
                if cube in self.engine.cache or cube in self.sessions._states:self._touch(cube)
                yield result
            finally:
                if workspace_entered:workspace.__exit__(None,None,None)
                self._pins[cube]-=1
                if not self._pins[cube]:self._pins.pop(cube)
                if cube in self.engine.cache or cube in self.sessions._states:self._touch(cube)
                if ref:
                    with self.store.lock:
                        self.store.pins[(cube,ref)]-=1
                        if not self.store.pins[(cube,ref)]:self.store.pins.pop((cube,ref))

    def _source(self,cube,expected,signature=None):
        actual=self.engine.source_identity(cube)
        if actual[0]!=expected or (signature is not None and actual[1]!=signature):
            raise DataError('SOURCE_CHANGED','源文件在分割读取或提交期间变化，原工作态未覆盖')
        return actual

    def _attach(self,cube,result):
        self._attachment_guard(cube)
        old=self.sessions._states.get(cube)
        # Stage the mutable containers so failure does not clear old candidates.
        if old is not None:
            staged=copy(old);staged.candidates=list(old.candidates);staged.gestures=dict(old.gestures);staged.undo_stack=deque(old.undo_stack,maxlen=old.undo_stack.maxlen)
            self.sessions._states[cube]=staged
        try:
            self.sessions.set_segmentation(cube,result)
            state=self.sessions._states[cube];state.segmentation_ref=result.segmentation_ref
            if old is not None and old.segmentation_ref and old.segmentation_ref!=result.segmentation_ref:
                state.candidates.clear();state.gestures.clear()
                previews=getattr(self.sessions,'_orchestration_previews',{})
                for key in [k for k,v in previews.items() if v['cube_id']==cube]:previews.pop(key)
                state.segmentation_notice='分割已更换，旧候选与手势已失效；像素标注与撤销历史保留。'
        except BaseException:
            if old is None:self.sessions._states.pop(cube,None)
            else:self.sessions._states[cube]=old
            raise

    def _attachment_guard(self,cube):
        """Restoring derived data must not trigger the legacy label-remap CAS."""
        from .draft import remap_document
        old=self.sessions._states.get(cube);ids=self.sessions._label_ids(cube)
        row=self.sessions.drafts.get(cube)
        if old is not None and old.label_ids!=ids:
            error=DataError('SEGMENTATION_STALE','类别工作态需先核查，读取分割不会修订草稿');error.status_code=409;raise error
        if row is not None:
            self.ensure(unique_bytes(row['document'])*3+32768,cube=cube)
            old_ids=old.label_ids if old is not None and old.revision==row['revision'] and old.document_json else None
            if remap_document(row['document'],self.sessions.drafts.labels(cube),old_ids)!=row['document']:
                error=DataError('SEGMENTATION_STALE','类别工作态需先核查，读取分割不会修订草稿');error.status_code=409;raise error

    def _read(self,cube,*,allow_resync=False):
        started=perf_counter();identity,signature=self.engine.source_identity(cube)
        info=self.store.inspect(cube,content_hash=identity)
        if info is None:return None,'missing',int((perf_counter()-started)*1000)
        registered,_=self.engine.registry.get(cube)
        if info['report']['shape']!=list(registered.shape):raise fail()
        self._attachment_guard(cube)
        cached=self.engine.cache.get(cube)
        if (cached and getattr(cached[1],'segmentation_ref',None)==info['ref'] and cached[0]!=info['params']
                and not allow_resync):
            error=DataError('SEGMENTATION_STALE','分割参数与当前引用不一致，请显式重新准备');error.status_code=409;raise error
        if (cached and getattr(cached[1],'segmentation_ref',None)==info['ref'] and cached[0]==info['params']
                and cached[1].content_hash==identity and cached[1].algorithm_version==ALGORITHM_VERSION):
            result=cached[1];origin='memory'
        else:
            self.ensure(info['bytes']+info['report']['shape'][0]*info['report']['shape'][1]*16+65536,cube=cube)
            with self.temporary(info['bytes']*3+1024**2):
                result=self.store.load(cube,content_hash=identity,info=info)
            origin='disk'
        self._source(cube,identity,signature)
        result.source_signature=signature
        state=self.sessions._states.get(cube)
        previews=getattr(self.sessions,'_orchestration_previews',None)
        old_previews=dict(previews) if previews is not None else None
        mismatch = (state is not None and state.segments is not None and state.segmentation_ref==info['ref']
                    and (state.params!=result.report['params'] or not np.array_equal(state.segments,result.segments)))
        if mismatch and not allow_resync:
            error=DataError('SEGMENTATION_STALE','分割与当前工作态不一致，请核查后显式重新准备');error.status_code=409;raise error
        try:
            if state is None or state.segments is None or state.segmentation_ref!=info['ref'] or mismatch:
                self.ensure((unique_bytes(result) if origin=='disk' else 0)+result.segments.nbytes*3+65536,cube=cube)
                self._attach(cube,result)
            self._source(cube,identity,signature)
            self.engine.cache[cube]=(info['params'],result);self._touch(cube)
            self.ensure(0,cube=cube)
        except BaseException:
            if state is None:self.sessions._states.pop(cube,None)
            else:self.sessions._states[cube]=state
            if cached is None:self.engine.cache.pop(cube,None)
            else:self.engine.cache[cube]=cached
            if old_previews is not None:
                previews.clear();previews.update(old_previews)
            raise
        return result,origin,int((perf_counter()-started)*1000)

    def read(self,cube):
        cube=str(cube)
        with self.lease(cube,required=False,restore=False):
            return self._read(cube)

    def status(self,cube):
        """Verified durability/recoverability without attaching or generating."""
        cube=str(cube)
        with self.lease(cube,required=False,restore=False):
            identity,_=self.engine.source_identity(cube)
            info=self.store.inspect(cube,content_hash=identity)
            return {'segmentation_ref':info['ref'] if info else None,'segmentation_durable':bool(info),
                    'segmentation_recoverable':bool(info)}

    def prepare(self,cube,params=Parameters(),*,force=False):
        cube=str(cube)
        with self.lease(cube,required=False,restore=False):
            identity,signature=self.engine.source_identity(cube)
            old_pointer=self.store.pointer_snapshot(cube)
            previous=self.engine.cache.get(cube);old_state=self.sessions._states.get(cube)
            previous_ref=getattr(previous[1],'segmentation_ref',None) if previous else None
            previews=getattr(self.sessions,'_orchestration_previews',None)
            old_previews=dict(previews) if previews is not None else None
            if previous and previous[1].content_hash is not None and previous[1].content_hash!=identity:
                raise DataError('SOURCE_CHANGED','源内容与已有分割不同，未覆盖工作态')
            self._attachment_guard(cube)
            try:info=self.store.inspect(cube,content_hash=identity)
            except DataError as error:
                if not force or error.code=='SEGMENTATION_STALE':raise
                info=None
            if not force and info is not None and info['params']==params:
                result,origin,_=self._read(cube,allow_resync=True)
                return result,'reused' if origin=='memory' else 'restored'
            dataset,_=self.engine.registry.readable(cube,raw=False);h,w,b=dataset.shape
            expected=self.expected_bytes(dataset.shape,params)
            self.ensure(expected,cube=cube)
            try:
                # Disk admission precedes any numerical work. The conservative
                # estimate includes payload headers, report and validation IO.
                with self.store.reserve(expected+4*1024**2),self.temporary(h*w*b*32+expected*3):
                    result=self.engine.generate(cube,params,force=force)
                    if result.report.get('shape')!=list(dataset.shape) or result.segments.shape!=tuple(dataset.shape[:2]):raise fail()
                    if previous is None:self.engine.cache.pop(cube,None)
                    else:self.engine.cache[cube]=previous
                    self.ensure(unique_bytes(result)+result.segments.nbytes*3+65536,cube=cube)
                    verify=lambda:self._source(cube,identity,signature)
                    verify()
                    ref=self.store.publish(cube,result,verify_source=verify,repair_invalid=force)
                    result.segmentation_ref=ref
                    # An existing immutable ref keeps its original compute
                    # report even if a force run reproduced identical arrays.
                    result.report=self.store.inspect(cube,ref=ref,content_hash=identity)['report']
                    verify()
                    self._attach(cube,result)
                    verify()
                    self.engine.cache[cube]=(params,result);self._touch(cube)
                    self.ensure(0,cube=cube)
                action='reused' if (not force and previous is not None and result is previous[1]) else 'generated'
                return result,action
            except BaseException:
                if previous is None:self.engine.cache.pop(cube,None)
                else:self.engine.cache[cube]=previous
                if previous is not None:previous[1].segmentation_ref=previous_ref
                if old_state is None:self.sessions._states.pop(cube,None)
                else:self.sessions._states[cube]=old_state
                if old_previews is not None:
                    previews.clear();previews.update(old_previews)
                try:
                    if self.store.pointer_snapshot(cube)!=old_pointer:self.store.restore_pointer(cube,old_pointer)
                except BaseException:
                    self.failed.add(cube)
                    error=DataError('CACHE_UNAVAILABLE','分割发布回滚失败，已停止后续写入');error.status_code=409;raise error from None
                raise

    def metrics(self):
        with self.engine.lock,self.sessions._lock:
            return {'retained_bytes':self.retained_bytes(),'retained_limit':self.retained_limit,
                    'temporary_reserved_bytes':self._temporary,'peak_temporary_reserved_bytes':self.peak_temporary_bytes,
                    'resident_cubes':len(self.engine.cache),'pinned_cubes':len(set(self._pins) | set(self._canvas_focus.values())),
                    'disk_bytes':self.store.usage(),'disk_reserved_bytes':self.store.reserved}

    def invalidate(self,cube):
        """Called after deletion CAS under coordinator.exclusive, before erase."""
        cube=str(cube)
        with self.engine.lock,self.sessions._lock:
            if self._pins.get(cube):raise budget_error() # coordinator excludes active operations before DB deletion
            for owner in [owner for owner, focused in self._canvas_focus.items() if focused == cube]:
                self._canvas_focus.pop(owner)  # An explicit deletion overrides a view-only cache pin.
            self.engine.cache.pop(cube,None);self.sessions._states.pop(cube,None);self._lru.pop(cube,None)
            self.failed.discard(cube)
            previews=getattr(self.sessions,'_orchestration_previews',{})
            for key in [k for k,v in previews.items() if v['cube_id']==cube]:previews.pop(key)
            for service in self._batches:
                for key in [k for k,v in service.receipts.items() if any(item['cube_id']==cube for item in v.get('items',[]))]:
                    service.receipts.pop(key)
            with self.store.lock:
                for key in [key for key in self.store.access if key[0]==cube]:self.store.access.pop(key)

    def cleanup(self):
        from backend.database import connect_database
        with self.engine.registry.recycle.coordinator.job(),self.engine.lock,self.sessions._lock:
            with connect_database(self.engine.registry.database) as db:
                existing={row[0] for row in db.execute('SELECT id FROM dataset_registry')}
            return self.store.cleanup(existing)
