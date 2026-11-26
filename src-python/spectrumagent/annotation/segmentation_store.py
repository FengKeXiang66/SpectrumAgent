"""Immutable numeric segmentation artifacts. No pickle, fitted models or business DDL.

The resource service serializes cube operations under engine -> session locks.
This store's lock only protects disk reservations/LRU; it never calls that service.
All mutations go through the existing storage guard. Reads never create a path.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
from threading import RLock
from uuid import UUID, uuid4

import numpy as np

from spectrumagent.data import DataError
from spectrumagent.storage import guard
from .engines.superpixels import algorithm_version, Parameters, Segmentation

SCHEMA_VERSION = 1
DISK_LIMIT = 8 * 1024**3
MAX_PAYLOAD_BYTES = 128 * 1024**2
MAX_JSON_BYTES = 2 * 1024**2
REF = re.compile(r's-[0-9a-f]{64}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')
# File names and array schemas are code-owned, never taken from manifest paths.
ARRAYS = {'segments': ('<i4', 2), 'initial_segments': ('<i4', 2),
          'mean_spectra': ('<f8', 2), 'std_spectra': ('<f8', 2),
          'normalized': ('<f4', 3), 'zscore': ('<f4', 3),
          'mean': ('<f8', 1), 'std': ('<f8', 1), 'reference_zscore5': ('<f4', 3)}
REPORT_KEYS = frozenset('cube_id shape params n_before n_after superpixel_count area_cv R internal_sum boundary_sum internal_pairs boundary_pairs sum_ratio_diagnostic d_s tau subdivided_ids parent_children feature_bytes resident_feature_bytes feature_mean feature_std normalized_mean normalized_std normalized_min normalized_max baseline_rss_bytes baseline_peak_rss_bytes peak_rss_bytes peak_rss_delta_bytes pca_seconds slic_seconds total_seconds overlay'.split())


def fail(code='SEGMENTATION_CORRUPT'):
    messages = {'SEGMENTATION_CORRUPT': '分割产物损坏，未自动重新计算',
                'SEGMENTATION_INCOMPATIBLE': '分割格式或算法不兼容，请显式重新准备',
                'SEGMENTATION_STALE': '分割与当前源内容不一致，未自动重新计算',
                'CACHE_UNAVAILABLE': '分割存储暂不可用，未更改原结果',
                'CACHE_DISK_BUDGET': '分割缓存磁盘预算不足，未提交新结果'}
    error = DataError(code, messages[code]);error.status_code = 409
    return error


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as src:
        for block in iter(lambda: src.read(1024**2), b''):h.update(block)
    return h.hexdigest()


def cube_uuid(cube):
    text = str(cube)
    try:
        if str(UUID(text)) != text:raise fail()
    except (ValueError,TypeError,AttributeError):raise fail() from None
    return text


def payload(result):
    return {**{k: getattr(result, k) for k in ('segments', 'initial_segments', 'mean_spectra', 'std_spectra', 'reference_zscore5')},
            **{k: getattr(result.features, k) for k in ('normalized', 'zscore', 'mean', 'std')}}


@dataclass(frozen=True)
class RestoredFeatures:
    """Read-only numeric view. It deliberately has no fitted PCA object."""
    normalized: np.ndarray
    zscore: np.ndarray
    mean: np.ndarray
    std: np.ndarray
    pca_batch_size: int


class SegmentationStore:
    def __init__(self, paths, *, disk_limit=DISK_LIMIT):
        self.root = paths.segmentation_cache
        self.disk_limit = disk_limit
        self.lock = RLock()
        self.reserved = 0
        self.pins = {}
        self.access = {}
        self._tick = 0

    def directory(self, cube):
        base = self.root / cube_uuid(cube)
        # Resolve every component, including symlinks/junctions; no alias dirs.
        if base.resolve() != base.absolute() or self.root.resolve() != self.root.absolute():raise fail()
        return base

    def _file(self, directory, name):
        p = directory / name
        if p.resolve() != p.absolute() or not p.resolve().is_relative_to(self.root.resolve()):raise fail()
        return p

    def _json(self, p):
        if p.stat().st_size > MAX_JSON_BYTES:raise fail()
        return json.loads(p.read_text('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))

    def active(self, cube):
        base = self.directory(cube);p = self._file(base, 'active.json')
        if not p.exists():return None
        try:
            doc = self._json(p)
            if isinstance(doc,dict) and type(doc.get('schema_version')) is int and doc['schema_version']!=SCHEMA_VERSION:
                raise fail('SEGMENTATION_INCOMPATIBLE')
            if (set(doc) != {'schema_version', 'cube_id', 'segmentation_ref'} or type(doc['schema_version']) is not int
                    or doc['schema_version'] != SCHEMA_VERSION):raise fail()
            if doc['cube_id'] != str(cube) or not isinstance(doc['segmentation_ref'], str) or not REF.fullmatch(doc['segmentation_ref']):raise fail()
            return doc['segmentation_ref']
        except (ValueError, KeyError, TypeError):raise fail() from None
        except OSError:raise fail('CACHE_UNAVAILABLE') from None

    @staticmethod
    def description(cube, result):
        params = result.report['params']
        if set(params) != {f.name for f in fields(Parameters)} | {'pca_batch_size'}:raise fail()
        if not HEX.fullmatch(result.content_hash or ''):raise fail()
        if any(type(params[k]) not in (int,float) or not math.isfinite(params[k]) or params[k]<=0 for k in ('compactness','k')):raise fail()
        params={**params, 'compactness':float(params['compactness']), 'k':float(params['k'])}
        return {'schema_version': SCHEMA_VERSION, 'cube_id': cube_uuid(cube),
                'content_hash': result.content_hash, 'params': params, 'algorithm_version': result.algorithm_version}

    def inspect(self, cube, *, ref=None, content_hash=None, _temporary=None, _touch=True):
        """Validate identity, byte headers, checksums and dimensions before loading."""
        try:
            ref = ref or self.active(cube)
            if ref is None:return None
            if not isinstance(ref, str) or not REF.fullmatch(ref):raise fail()
            base = self.directory(cube)
            directory = base / ref
            if _temporary is not None:
                if _temporary.parent != base or not re.fullmatch(r'\.tmp-[0-9a-f]{32}', _temporary.name):raise fail()
                directory = _temporary
            manifest = self._json(self._file(directory, 'manifest.json'))
            if set(manifest) != {'description', 'input_key', 'segmentation_ref', 'arrays', 'aliases', 'report'}:raise fail()
            desc = manifest['description']
            if type(desc.get('schema_version')) is not int or desc.get('schema_version') != SCHEMA_VERSION or desc.get('algorithm_version') != algorithm_version():raise fail('SEGMENTATION_INCOMPATIBLE')
            if set(desc) != {'schema_version','cube_id','content_hash','params','algorithm_version'} or desc['cube_id'] != str(cube):raise fail()
            if not HEX.fullmatch(desc['content_hash']):raise fail()
            if content_hash is not None and desc['content_hash'] != content_hash:raise fail('SEGMENTATION_STALE')
            key = hashlib.sha256(canonical(desc)).hexdigest()
            if key != manifest['input_key'] or manifest['segmentation_ref'] != ref:raise fail()
            expected_ref = 's-' + hashlib.sha256(canonical({'input_key': key, 'arrays': manifest['arrays'], 'aliases': manifest['aliases']})).hexdigest()
            if expected_ref != ref:raise fail()
            inventory, aliases = manifest['arrays'], manifest['aliases']
            if aliases not in ({}, {'reference_zscore5':'zscore'}) or set(inventory) != set(ARRAYS)-set(aliases):raise fail()
            allowed = {'manifest.json', 'report.json'} | {k+'.npy' for k in inventory}
            if {p.name for p in directory.iterdir()} != allowed:raise fail()
            total = 0;shapes = {}
            for name, meta in inventory.items():
                if set(meta) != {'dtype','shape','size','sha256'}:raise fail()
                p = self._file(directory, name+'.npy')
                if type(meta['size']) is not int or not 0 < meta['size'] <= MAX_PAYLOAD_BYTES or p.stat().st_size != meta['size']:raise fail()
                with p.open('rb') as stream:
                    version = np.lib.format.read_magic(stream)
                    if version == (1, 0):shape, order, dtype = np.lib.format.read_array_header_1_0(stream)
                    elif version == (2, 0):shape, order, dtype = np.lib.format.read_array_header_2_0(stream)
                    else:raise fail()
                    if order or dtype.str != ARRAYS[name][0] or dtype.hasobject or len(shape) != ARRAYS[name][1]:raise fail()
                    if any(type(n) is not int or n <= 0 or n > MAX_PAYLOAD_BYTES for n in shape):raise fail()
                    nbytes = math.prod(shape) * dtype.itemsize
                    if nbytes > MAX_PAYLOAD_BYTES or stream.tell()+nbytes != meta['size']:raise fail()
                total += nbytes
                if (total > MAX_PAYLOAD_BYTES or not isinstance(meta['shape'],list)
                        or any(type(n) is not int for n in meta['shape']) or list(shape) != meta['shape'] or dtype.str != meta['dtype']):raise fail()
                if digest(p) != meta['sha256']:raise fail()
                shapes[name] = shape
            shapes.update({name: shapes[target] for name,target in aliases.items()})
            params = desc['params'];keys = {f.name for f in fields(Parameters)}
            if set(params) != keys | {'pca_batch_size'}:raise fail()
            params_obj = Parameters(**{k:params[k] for k in keys})
            for k in ('n_segments','pca_components','block_size','pca_batch_size'):
                if type(params[k]) is not int or params[k] <= 0:raise fail()
            if params['n_segments'] > 65535 or params['feature_version'] != Parameters().feature_version:raise fail('SEGMENTATION_INCOMPATIBLE')
            if any(type(params[k]) not in (float,int) or not math.isfinite(params[k]) or params[k]<=0 for k in ('compactness','k')):raise fail()
            h,w = shapes['segments'];components=params_obj.pca_components
            if (shapes['mean_spectra'][1]<5 or components>shapes['mean_spectra'][1]
                    or shapes['initial_segments'] != (h,w) or shapes['normalized'] != (h,w,components)
                    or shapes['zscore'] != (h,w,components) or shapes['reference_zscore5'] != (h,w,5)
                    or shapes['mean'] != (components,) or shapes['std'] != (components,)
                    or shapes['mean_spectra'] != shapes['std_spectra'] or shapes['mean_spectra'][0] > min(h*w,65536)
                    or params['pca_batch_size'] != params['block_size']*w):raise fail()
            report_meta = manifest['report'];report_path=self._file(directory,'report.json')
            if set(report_meta) != {'size','sha256'} or report_path.stat().st_size != report_meta['size'] or digest(report_path)!=report_meta['sha256']:raise fail()
            report=self._json(report_path)
            if (set(report)!=REPORT_KEYS or report['cube_id'] != str(cube) or report['params'] != params
                    or not isinstance(report['shape'],list) or any(type(n) is not int for n in report['shape'])
                    or report['shape'] != [h,w,shapes['mean_spectra'][1]]
                    or report['superpixel_count'] != shapes['mean_spectra'][0] or report['n_after'] != report['superpixel_count']):raise fail()
            if type(report['n_before']) is not int or not 0<report['n_before']<=min(h*w,65536):raise fail()
            complex_keys={'cube_id','shape','params','parent_children','subdivided_ids','overlay','d_s','feature_mean','feature_std','normalized_mean','normalized_std'}
            for name in REPORT_KEYS-complex_keys:
                value=report[name]
                if value is None and name in ('R','sum_ratio_diagnostic'):continue
                if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise fail()
            for name in ('n_before','n_after','superpixel_count','feature_bytes','resident_feature_bytes','internal_pairs','boundary_pairs',
                         'baseline_rss_bytes','baseline_peak_rss_bytes','peak_rss_bytes','peak_rss_delta_bytes'):
                if type(report[name]) is not int:raise fail()
            for name in ('d_s','feature_mean','feature_std','normalized_mean','normalized_std'):
                values=report[name];length=report['n_before'] if name=='d_s' else components
                if not isinstance(values,list) or len(values)!=length or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise fail()
            if not isinstance(report['subdivided_ids'],list) or any(type(n) is not int or not 0<=n<report['n_before'] for n in report['subdivided_ids']):raise fail()
            if not isinstance(report['parent_children'],dict) or any(not k.isdecimal() or str(int(k))!=k for k in report['parent_children']):raise fail()
            for key,values in report['parent_children'].items():
                if not 0<=int(key)<report['n_before'] or not isinstance(values,list) or not values or any(type(n) is not int or not 0<=n<report['n_after'] for n in values):raise fail()
            report['parent_children']={int(k):v for k,v in report['parent_children'].items()}
            overlay=report['overlay']
            if not isinstance(overlay,dict) or set(overlay)!={'width','height','png_base64'}:raise fail()
            if any(type(overlay[k]) is not int or not 0<overlay[k]<=512 for k in ('width','height')) or not isinstance(overlay['png_base64'],str):raise fail()
            try:
                from io import BytesIO
                from PIL import Image
                with Image.open(BytesIO(base64.b64decode(overlay['png_base64'],validate=True))) as image:
                    if image.format!='PNG' or image.size!=(overlay['width'],overlay['height']):raise fail()
                    image.verify()
            except (ValueError,OSError,Image.DecompressionBombError):raise fail() from None
            # Scan finite values and block ranges in bounded buffers BEFORE a
            # resource-service allocation is admitted. No memmap handles persist.
            for name in inventory:
                seen = set()
                with self._file(directory,name+'.npy').open('rb') as stream:
                    version=np.lib.format.read_magic(stream)
                    (np.lib.format.read_array_header_1_0 if version==(1,0) else np.lib.format.read_array_header_2_0)(stream)
                    while block:=stream.read(1024**2):
                        values=np.frombuffer(block,dtype=ARRAYS[name][0])
                        if not np.isfinite(values).all():raise fail()
                        if name in ('std','std_spectra') and np.any(values<0):raise fail()
                        if name=='normalized' and (np.any(values<0) or np.any(values>1)):raise fail()
                        if name in ('segments','initial_segments'):
                            limit=report['superpixel_count'] if name=='segments' else report['n_before']
                            if values.min()<0 or values.max()>=limit:raise fail()
                            seen.update(np.unique(values).tolist())
                if name in ('segments','initial_segments') and len(seen)!=limit:raise fail()
            if _touch:
                with self.lock:
                    self._tick += 1;self.access[(str(cube),ref)] = self._tick
            return {'ref':ref,'directory':directory,'manifest':manifest,'report':report,'bytes':total,'params':params_obj}
        except DataError:raise
        except FileNotFoundError:raise fail() from None
        except OSError:raise fail('CACHE_UNAVAILABLE') from None
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError, EOFError):raise fail() from None

    def load(self, cube, *, content_hash, info=None):
        info = info or self.inspect(cube, content_hash=content_hash)
        if info is None:return None
        arrays = {}
        try:
            for name in info['manifest']['arrays']:
                p=self._file(info['directory'],name+'.npy')
                # Check again after allocation admission; a file swapped during
                # validation must not escape the validated byte/shape envelope.
                with p.open('rb') as stream:
                    raw=stream.read(MAX_PAYLOAD_BYTES+1)
                meta=info['manifest']['arrays'][name]
                if len(raw)!=meta['size'] or hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise fail()
                from io import BytesIO
                a=np.load(BytesIO(raw),allow_pickle=False)
                if a.dtype.str!=meta['dtype'] or list(a.shape)!=meta['shape'] or not np.isfinite(a).all():raise fail()
                a.flags.writeable=False;arrays[name]=a
            arrays.update({name:arrays[target] for name,target in info['manifest']['aliases'].items()})
            segments=arrays['segments'];initial=arrays['initial_segments'];report=info['report']
            if (segments.min()<0 or segments.max()>=report['superpixel_count']
                    or len(np.unique(segments))!=report['superpixel_count'] or initial.min()<0
                    or initial.max()>=report['n_before'] or len(np.unique(initial))!=report['n_before']):raise fail()
            if np.any(arrays['std_spectra']<0) or np.any(arrays['std']<0):raise fail()
            features=RestoredFeatures(*(arrays[k] for k in ('normalized','zscore','mean','std')), report['params']['pca_batch_size'])
            result=Segmentation(*(arrays[k] for k in ('segments','initial_segments','mean_spectra','std_spectra')),features,
                                arrays['reference_zscore5'],report,content_hash,algorithm_version())
            result.segmentation_ref=info['ref']
            return result
        except DataError:raise
        except OSError:raise fail('CACHE_UNAVAILABLE') from None
        except (ValueError,TypeError,KeyError):raise fail() from None

    def usage(self):
        """Unknown files consume quota, but are never adopted or recursively deleted."""
        if not self.root.exists():return 0
        if self.root.resolve()!=self.root.absolute():raise fail()
        total=0
        for directory, dirs, files in os.walk(self.root,followlinks=False):
            dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()
                     and not (Path(directory)/d).is_junction() and (Path(directory)/d).resolve()==(Path(directory)/d).absolute()]
            for name in files:
                p=Path(directory)/name
                if p.is_symlink() or p.resolve()!=p.absolute():continue
                total+=p.stat().st_size
        return total

    def _remove(self, cube, path):
        base=self.directory(cube)
        if path.parent != base or not (REF.fullmatch(path.name) or re.fullmatch(r'\.tmp-[0-9a-f]{32}',path.name)):raise fail()
        if path.resolve()!=path.absolute() or any(p.is_symlink() or p.resolve()!=p.absolute() for p in path.rglob('*')):raise fail()
        guard.rmtree(path)

    def collect(self, required=0):
        """Only verified, unpinned non-current variants; malformed paths stay put."""
        with self.lock:
            choices=[]
            if not self.root.exists():return
            for cube_dir in self.root.iterdir():
                try:
                    cube=cube_uuid(cube_dir.name);self.directory(cube);active=self.active(cube)
                    for item in cube_dir.iterdir():
                        if REF.fullmatch(item.name) and item.name!=active and not self.pins.get((cube,item.name)):
                            self.inspect(cube,ref=item.name,_touch=False)
                            choices.append((self.access.get((cube,item.name),0),cube,item))
                except (DataError,ValueError,OSError):continue
            for _,cube,item in sorted(choices,key=lambda row:row[0]):
                if self.usage()+self.reserved+required<=self.disk_limit:break
                self._remove(cube,item)
                self.access.pop((cube,item.name),None)

    def cleanup(self, existing_cubes):
        """Owned crash temps/orphans only; unknown/reparse entries are reported."""
        removed=[];refused=[]
        with self.lock:
            if not self.root.exists():return {'removed':removed,'refused':refused}
            if self.root.resolve()!=self.root.absolute():raise fail()
            for base in self.root.iterdir():
                try:
                    cube=cube_uuid(base.name)
                    self.directory(cube)
                    if any(key[0]==cube and n for key,n in self.pins.items()):continue
                    active=self.active(cube)
                    entries=list(base.iterdir())
                    for p in entries:
                        if p.name=='active.json':continue
                        if REF.fullmatch(p.name):self.inspect(cube,ref=p.name,_touch=False)
                        elif re.fullmatch(r'\.tmp-[0-9a-f]{32}',p.name):
                            allowed={'manifest.json','report.json'}|{k+'.npy' for k in ARRAYS}
                            if any(c.name not in allowed or not c.is_file() or c.resolve()!=c.absolute() for c in p.iterdir()):raise fail()
                        elif re.fullmatch(r'\.active-[0-9a-f]{32}',p.name) and p.is_file() and p.resolve()==p.absolute():pass
                        else:raise fail()
                    if cube not in existing_cubes:
                        # All descendants were checked above; only this exact
                        # canonical cube root, never cache/root, can be removed.
                        if base.resolve()!=base.absolute():raise fail()
                        guard.rmtree(base);removed.append(cube)
                        for key in [key for key in self.access if key[0]==cube]:self.access.pop(key)
                    else:
                        for p in entries:
                            if re.fullmatch(r'\.tmp-[0-9a-f]{32}',p.name):self._remove(cube,p);removed.append(cube+'/'+p.name)
                            elif re.fullmatch(r'\.active-[0-9a-f]{32}',p.name):guard.unlink(p);removed.append(cube+'/'+p.name)
                except (DataError,ValueError,OSError):refused.append(base.name)
            self.collect()
        return {'removed':removed,'refused':refused}

    @contextmanager
    def reserve(self, amount):
        with self.lock:
            self.collect(amount)
            parent=self.root
            while not parent.exists():parent=parent.parent
            if amount<0 or self.usage()+self.reserved+amount>self.disk_limit or shutil.disk_usage(parent).free<self.reserved+amount:
                raise fail('CACHE_DISK_BUDGET')
            self.reserved+=amount
        try:yield
        finally:
            with self.lock:self.reserved-=amount

    def _write(self,path,value,*,array=False):
        p=guard.resolve_write(path,kind='SEGMENTATION_ARRAY' if array else 'SEGMENTATION_MANIFEST')
        with p.open('xb') as stream:
            if array:np.save(stream,value,allow_pickle=False)
            else:stream.write(canonical(value))
            stream.flush();os.fsync(stream.fileno())

    def point(self,cube,ref):
        """Explicit pointer replacement, also used for normal-exception rollback."""
        base=self.directory(cube);active=self._file(base,'active.json')
        if ref is None:
            if active.exists():guard.unlink(active)
            return
        if not REF.fullmatch(ref):raise fail()
        tmp=self._file(base,'.active-'+uuid4().hex)
        try:
            self._write(tmp,{'schema_version':SCHEMA_VERSION,'cube_id':str(cube),'segmentation_ref':ref})
            guard.replace(tmp,active)
        finally:
            if tmp.exists():guard.unlink(tmp)

    def pointer_snapshot(self,cube):
        try:
            path=self._file(self.directory(cube),'active.json')
            if not path.exists():return None
            if path.stat().st_size>MAX_JSON_BYTES:raise fail()
            return path.read_bytes()
        except OSError:raise fail('CACHE_UNAVAILABLE') from None

    def restore_pointer(self,cube,snapshot):
        base=self.directory(cube);active=self._file(base,'active.json')
        if snapshot is None:
            if active.exists():guard.unlink(active)
            return
        tmp=self._file(base,'.active-'+uuid4().hex)
        try:
            with guard.resolve_write(tmp,kind='SEGMENTATION_POINTER_ROLLBACK').open('xb') as out:
                out.write(snapshot);out.flush();os.fsync(out.fileno())
            guard.replace(tmp,active)
        finally:
            if tmp.exists():guard.unlink(tmp)

    def publish(self,cube,result,*,verify_source,repair_invalid=False):
        """Return immutable ref after complete reread, then publish explicit active."""
        cube=cube_uuid(cube);arrays=payload(result);desc=self.description(cube,result)
        aliases={}
        if arrays['reference_zscore5'] is arrays['zscore']:aliases={'reference_zscore5':'zscore'}
        estimate=sum(a.nbytes+256 for k,a in arrays.items() if k not in aliases)+MAX_JSON_BYTES*2
        base=self.directory(cube);tmp=base/('.tmp-'+uuid4().hex)
        ref=None
        # Existing Windows guard uses normal Win32 paths. Refuse a path that
        # cannot address every immutable child BEFORE publishing its directory.
        if os.name=='nt' and len(str(base/('s-'+'0'*64)/'reference_zscore5.npy'))>=260:
            raise fail('CACHE_UNAVAILABLE')
        try:
            with self.reserve(estimate):
                guard.mkdir(base,parents=True,exist_ok=True);guard.mkdir(tmp)
                inventory={}
                for name,a in arrays.items():
                    if name in aliases:continue
                    if a.dtype.str!=ARRAYS[name][0] or a.ndim!=ARRAYS[name][1] or not np.isfinite(a).all():raise fail()
                    path=self._file(tmp,name+'.npy');self._write(path,a,array=True)
                    inventory[name]={'dtype':a.dtype.str,'shape':list(a.shape),'size':path.stat().st_size,'sha256':digest(path)}
                rp=self._file(tmp,'report.json');self._write(rp,result.report)
                key=hashlib.sha256(canonical(desc)).hexdigest()
                ref='s-'+hashlib.sha256(canonical({'input_key':key,'arrays':inventory,'aliases':aliases})).hexdigest()
                manifest={'description':desc,'input_key':key,'segmentation_ref':ref,'arrays':inventory,'aliases':aliases,
                          'report':{'size':rp.stat().st_size,'sha256':digest(rp)}}
                self._write(self._file(tmp,'manifest.json'),manifest)
                # Same reader validates our owned temporary object BEFORE the
                # immutable directory is published; active remains untouched.
                self.inspect(cube,ref=ref,content_hash=result.content_hash,_temporary=tmp)
                target=base/ref
                verify_source()
                if target.exists():
                    try:self.inspect(cube,ref=ref,content_hash=result.content_hash)
                    except DataError:
                        if not repair_invalid:raise
                        # Explicit preparation may quarantine a damaged object;
                        # never overwrite a file used by another live lease.
                        if self.pins.get((cube,ref),0)>1 or target.resolve()!=target.absolute():raise fail('CACHE_UNAVAILABLE')
                        allowed={'manifest.json','report.json'}|{k+'.npy' for k in ARRAYS}
                        if any(p.name not in allowed or not p.is_file() or p.resolve()!=p.absolute() for p in target.iterdir()):raise fail()
                        guard.replace(target,base/('.bad-'+uuid4().hex))
                if not target.exists():
                    guard.replace(tmp,target)
                    try:self.load(cube,content_hash=result.content_hash,info=self.inspect(cube,ref=ref,content_hash=result.content_hash))
                    except BaseException:
                        self._remove(cube,target);raise
                verify_source()
                self.point(cube,ref)
                return ref
        except DataError:raise
        except OSError:raise fail('CACHE_UNAVAILABLE') from None
        finally:
            if tmp.exists():self._remove(cube,tmp)
            if ref is not None and not (base/ref).exists():self.access.pop((cube,ref),None)
