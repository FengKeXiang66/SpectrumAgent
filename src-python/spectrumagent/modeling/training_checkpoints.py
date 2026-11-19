"""Atomic, hash-verified fold units; partial truth never includes unfinished rows."""
import hashlib
import json
import re
from pathlib import PurePosixPath
from uuid import uuid4

import numpy as np
from backend.database import connect_database
from spectrumagent.storage import guard as storage
from . import ModelingError
from .evaluation import encode, digest, summarize


def array_digest(value):
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def prepare(control, data, folds, protocol, threshold, support):
    identity = {'body': control.binding['body'], 'code_identity': control.binding['code_identity'],
                'cubes': data['cubes'], 'classes': data['classes'], 'pipeline': data['pipeline'],
                'axis': [data['wavelengths'], data['wavelength_unit']],
                'arrays': {k: array_digest(data[k]) for k in ('y', 'groups', 'cube_index', 'flat_index')},
                'folds': [{'fold_index': f['fold_index'], 'train': array_digest(f['train_idx']),
                           'test': array_digest(f['test_idx'])} for f in folds]}
    control.signature = digest(identity)
    control.data = data
    control.meta = {'n_pixels': len(data['y']), 'n_images': len(data['cubes']), 'n_samples': len(np.unique(data['groups'])),
                    'classes': data['classes'], 'group_kind': data['group_kind'], 'protocol': protocol,
                    'threshold': threshold, 'total_folds': len(folds), 'class_support': support}
    control.units = {}
    control.fold_indices = {f['fold_index']: f['test_idx'] for f in folds}
    if control.parent:
        with connect_database(control.service.database) as db:
            rows = db.execute('SELECT unit,manifest FROM training_checkpoint WHERE job_id=?', (control.parent,)).fetchall()
        for unit, raw in rows:
            manifest = json.loads(raw)
            if manifest['signature'] != control.signature:
                raise ModelingError('CHECKPOINT_IDENTITY_MISMATCH', '原任务输入、分折或算法身份已变化，不能继续')
            verify(control.service, manifest, unit)
            control.units[unit] = manifest


def path_for(service, relative):
    path = PurePosixPath(relative)
    base = (service.runs.paths.root/'models').resolve()
    target = base.joinpath(*path.parts).resolve()
    if path.is_absolute() or '..' in path.parts or '\\' in relative or ':' in relative or not target.is_relative_to(base):
        raise ModelingError('INVALID_CHECKPOINT_PATH', '检查点路径非法')
    return target


def verify(service, manifest, unit=None):
    if not isinstance(manifest,dict) or manifest.get('schema') != 1:
        raise ModelingError('CHECKPOINT_FORMAT_UNSUPPORTED', '检查点格式不受支持，请重新训练')
    if not isinstance(manifest.get('unit'),str) or not re.fullmatch(r'final|fold-\d+-(selected|baseline)',manifest['unit']):
        raise ModelingError('CHECKPOINT_FORMAT_UNSUPPORTED', '检查点单元格式非法')
    if unit is not None and manifest['unit'] != unit:
        raise ModelingError('CHECKPOINT_IDENTITY_MISMATCH', '检查点单元与登记身份不一致')
    for file in manifest['files'].values():
        path = path_for(service, file['path'])
        if not path.is_file() or service.file_hash(path) != file['sha256']:
            raise ModelingError('CHECKPOINT_HASH_MISMATCH', '检查点缺失或摘要不一致，请重新训练')


def save(control, unit, pack, indices=None, probabilities=None):
    control.check()
    service = control.service
    run_id = service.status(control.identifier)['run_id']
    folder = service.runs.paths.root/'models'/run_id/'training-checkpoints'/control.identifier
    storage.mkdir(folder, parents=True, exist_ok=True)
    stem = unit+'-'+str(uuid4())
    files, created = {}, []
    manifest = {'schema': 1, 'source_job_id': control.identifier, 'unit': unit, 'signature': control.signature,
                'meta': control.meta, 'files': files}
    try:
        document = folder/(stem+'.json')
        temp = document.with_suffix('.json.part')
        created.append(temp)
        storage.resolve_write(temp, kind='WRITE_BYTES').write_text(encode(pack), 'utf-8')
        storage.replace(temp, document); created.append(document)
        files['model'] = {'path': document.relative_to(service.runs.paths.root/'models').as_posix(), 'sha256': service.file_hash(document)}
        if probabilities is not None:
            data = control.data
            observations = {k: data[k][indices] for k in ('y', 'groups', 'cube_index', 'flat_index')}
            observations['probabilities'] = probabilities
            observations['fold_index'] = np.full(len(indices), int(unit.split('-')[1]), np.int32)
            arrays = folder/(stem+'.npz'); temp = arrays.with_suffix('.npz.part'); created.append(temp)
            with storage.resolve_write(temp, kind='WRITE_BYTES').open('wb') as stream:
                np.savez_compressed(stream, **observations)
            storage.replace(temp, arrays); created.append(arrays)
            files['observations'] = {'path': arrays.relative_to(service.runs.paths.root/'models').as_posix(), 'sha256': service.file_hash(arrays)}
        verify(service, manifest, unit)
        with connect_database(service.database) as db:
            db.execute('INSERT INTO training_checkpoint VALUES (?,?,?)', (control.identifier, unit, encode(manifest)))
        control.units[unit] = manifest
    except BaseException:
        for path in created:
            if path.exists(): storage.unlink(path)
        raise
    # Finish committing a unit even if a cancellation arrived during its write.
    service.event(control.identifier, 'checkpoint', {'unit': unit})


def reuse(control, unit):
    manifest = control.units.get(unit)
    if not manifest:
        return None
    control.check()
    verify(control.service, manifest, unit)
    model = json.loads(path_for(control.service, manifest['files']['model']['path']).read_text('utf-8'))
    arrays = None
    if 'observations' in manifest['files']:
        with np.load(path_for(control.service, manifest['files']['observations']['path']), allow_pickle=False) as data:
            arrays = {k: data[k].copy() for k in data.files}
        index=int(unit.split('-')[1]);indices=control.fold_indices[index]
        if any(not np.array_equal(arrays[k],control.data[k][indices]) for k in ('y','groups','cube_index','flat_index')) or not np.all(arrays['fold_index']==index):
            raise ModelingError('CHECKPOINT_IDENTITY_MISMATCH', '检查点观测与实际分折不一致')
        probabilities=arrays['probabilities']
        if probabilities.shape!=(len(indices),len(control.data['classes'])) or not np.isfinite(probabilities).all() or np.any(probabilities<0) or np.any(probabilities>1) or not np.allclose(probabilities.sum(axis=1),1):
            raise ModelingError('INVALID_CHECKPOINT_PREDICTION', '检查点分类得分非法')
    if manifest['source_job_id'] != control.identifier:
        with connect_database(control.service.database) as db:
            db.execute('INSERT OR IGNORE INTO training_checkpoint VALUES (?,?,?)', (control.identifier, unit, encode(manifest)))
        control.service.event(control.identifier, 'reused', {'unit': unit})
    return model, arrays


def partial(service, identifier, owner=None):
    receipt = service.status(identifier, owner=owner)
    with connect_database(service.database) as db:
        rows = db.execute("SELECT unit,manifest FROM training_checkpoint WHERE job_id=? AND unit LIKE 'fold-%-selected' ORDER BY unit", (identifier,)).fetchall()
    parts, meta = [], None
    for unit, raw in rows:
        manifest = json.loads(raw)
        verify(service, manifest, unit)
        meta = manifest['meta']
        with np.load(path_for(service, manifest['files']['observations']['path']), allow_pickle=False) as data:
            parts.append({k: data[k].copy() for k in data.files})
    result = {'job_id': identifier, 'complete': False, 'status': receipt['status'], 'reason': '评价不完整，仅包含有效的已完成折',
              'total_folds': receipt['total_folds'], 'completed_folds': receipt['completed_folds'],
              'baseline_completed_folds': receipt.get('baseline_folds', []), 'baseline_required': receipt.get('band_selection') == 'ipls',
              'n_evaluated_pixels': 0, 'n_planned_pixels': meta['n_pixels'] if meta else receipt.get('total_pixels'),
              'classes': meta['classes'] if meta else [], 'populations': None}
    if parts:
        all_rows = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
        probabilities = all_rows['probabilities']
        result.update(summarize(all_rows['y'], probabilities.argmax(axis=1), all_rows['groups'], probabilities.max(axis=1),
                                all_rows['fold_index'], labels=list(range(len(meta['classes']))), threshold=meta['threshold']))
        result['n_evaluated_pixels'] = len(all_rows['y'])
        result['completed_folds'] = sorted(set(map(int, all_rows['fold_index'])))
        result['class_support'] = meta['class_support']
    return result
