"""Draft/freeze training inputs; resolve successful runs only by exact identity."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
from uuid import UUID, uuid4

import numpy as np

from backend.database import connect_database
from backend.paths import AppPaths
from spectrumagent.data import DataError
from spectrumagent.preprocess.recipes import input_fingerprint
from spectrumagent.preprocess.run import file_sha256
from .migrations import migrate


def content_hash(members):
    identities = sorted((m['cube_id'], m['annotation_version_id'], m['recipe_version_id'],
                         m['input_fingerprint']) for m in members)
    return sha256('\n'.join('|'.join(row) for row in identities).encode('utf-8')).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _identifier(value):
    try:
        if not isinstance(value, str):
            raise ValueError
        return str(UUID(value))
    except (ValueError, AttributeError):
        raise DataError('INVALID_REQUEST', '训练集引用须为 UUID 字符串') from None


class TrainingSets:
    def __init__(self, registry, paths=None):
        self.registry, self.database = registry, registry.database
        self.paths = paths or AppPaths(registry.storage_guard.root)
        with self.registry.lock, connect_database(self.database) as db:
            migrate(db)

    def _prepare(self, db, member):
        cube, version, recipe = (member[key] for key in
                                  ('cube_id', 'annotation_version_id', 'recipe_version_id'))
        from spectrumagent.preprocess.drafts import assert_available
        assert_available(db,version_id=recipe)
        dataset, _ = self.registry.readable(cube, raw=True)
        annotation = db.execute('SELECT * FROM annotation_version WHERE id=?', (version,)).fetchone()
        if annotation is None or annotation['cube_id'] != cube:
            raise DataError('VERSION_CUBE_MISMATCH', '确认版标注不存在或不属于对应样品')
        if db.execute('SELECT 1 FROM preprocess_recipe_version v JOIN preprocess_recipe r ON r.id=v.recipe_id '
                      'WHERE v.id=?', (recipe,)).fetchone() is None:
            raise DataError('RECIPE_VERSION_NOT_FOUND', '预处理配方版本不存在')
        relative = PurePosixPath(annotation['snapshot_ref'])
        if (relative.is_absolute() or '..' in relative.parts or '\\' in annotation['snapshot_ref']
                or ':' in annotation['snapshot_ref']):
            raise DataError('INVALID_SNAPSHOT_REF', '标注快照须为 POSIX 相对路径')
        folder = self.paths.snapshots.joinpath(*relative.parts)
        if not folder.resolve().is_relative_to(self.paths.snapshots.resolve()):
            raise DataError('INVALID_SNAPSHOT_REF', '标注快照不能超出标注根目录')
        try:
            with np.load(folder / 'label_map.npz', allow_pickle=False) as archive:
                label_map = archive['label_map']
            label_index = json.loads((folder / 'label_index.json').read_text('utf-8'))
        except (OSError, ValueError, KeyError) as error:
            raise DataError('INVALID_SNAPSHOT_REF', '无法读取确认版标注快照') from error
        if (label_map.dtype != np.int32 or label_map.shape != dataset.shape[:2]
                or np.any(label_map < -2) or not isinstance(label_index, dict)):
            raise DataError('INVALID_SNAPSHOT_REF', '标注快照与样品轴序或编码不匹配')
        indices, counts = np.unique(label_map[label_map >= 0], return_counts=True)
        n_pixels = int(counts.sum())
        if not n_pixels:
            raise DataError('ANNOTATION_EMPTY', '训练集成员须有已确认的标注像素')
        project = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (cube,)).fetchone()[0]
        labels = Counter()
        for index, count in zip(indices, counts):
            label = label_index.get(str(index))
            if (not isinstance(label, str) or db.execute('SELECT 1 FROM label WHERE id=? AND project_id=?',
                                                       (label, project)).fetchone() is None):
                raise DataError('LABEL_PROJECT_MISMATCH', '快照类别未登记或不属于样品所在项目')
            labels[label] += int(count)
        files = {Path(dataset.header_path), Path(dataset.data_path)}
        root = Path(os.path.commonpath([str(path.parent) for path in files]))
        hashes = {path.relative_to(root).as_posix(): file_sha256(path) for path in sorted(files)}
        return {**member, 'label_id': None, 'input_fingerprint': input_fingerprint(cube, hashes, version, n_pixels),
                'n_pixels': n_pixels}, labels

    @staticmethod
    def _version(db, version_id):
        row = db.execute('SELECT * FROM training_set_version WHERE id=?', (version_id,)).fetchone()
        if row is None:
            raise DataError('TRAINING_SET_NOT_FOUND', '训练集版本不存在', version_id=version_id)
        result = dict(row)
        result['label_summary'] = json.loads(result['label_summary'])
        return result

    @staticmethod
    def _members(db, version_id):
        return [dict(row) for row in db.execute(
            'SELECT cube_id,label_id,annotation_version_id,recipe_version_id,input_fingerprint,n_pixels '
            'FROM training_set_member WHERE version_id=? ORDER BY cube_id', (version_id,))]

    def _snapshot(self, db, version_id):
        version = self._version(db, version_id)
        members = self._members(db, version_id)
        if (not members or len(members) != version['member_count']
                or content_hash(members) != version['content_hash']):
            raise DataError('TRAINING_SET_INCONSISTENT', '训练集版本成员数量或内容身份不完整')
        return version, members

    @staticmethod
    def _resolve(db, version_id, members):
        resolved, missing = [], []
        for member in members:
            # No recency ordering or cube/recipe fallback. Equal input identities
            # may have repeated executions; use a stable id to select one.
            run = db.execute("SELECT id FROM preprocess_run WHERE cube_id=? AND annotation_version_id=? "
                             "AND recipe_version_id=? AND status='succeeded' AND input_fingerprint=? "
                             'ORDER BY id LIMIT 1',
                             (member['cube_id'], member['annotation_version_id'], member['recipe_version_id'],
                              member['input_fingerprint'])).fetchone()
            resolved.append({**member, 'preprocess_run_id': run[0] if run else None})
            if run is None:
                missing.append({key: member[key] for key in
                                ('cube_id', 'annotation_version_id', 'recipe_version_id', 'input_fingerprint')})
        return {'version_id': version_id, 'members': resolved, 'need_preprocess': missing}

    def preview(self, scope):
        # Reuse the strict public scope contract for direct service callers too.
        from spectrumagent.api.training_sets import TrainingSetPreviewRequest
        request = TrainingSetPreviewRequest.model_validate(scope)
        self.registry.recycle.coordinator.check()
        with self.registry.lock, connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            prepared, summary, failures = [], Counter(), []
            for item in request.members:
                member = item.model_dump()
                try:
                    row, labels = self._prepare(db, member)
                    prepared.append(row)
                    summary.update(labels)
                except (DataError, OSError) as error:
                    if isinstance(error, OSError):
                        error = DataError('READ_FAILED', '训练集源文件无法读取')
                    failures.append({**member, **error.as_dict()})
            if failures:
                raise DataError('TRAINING_SET_INVALID', '训练集未登记；请修复全部成员缺口', failures=failures)
            digest = content_hash(prepared)
            previous = db.execute('SELECT id FROM training_set_version WHERE content_hash=? '
                                  'ORDER BY created_at,id LIMIT 1', (digest,)).fetchone()
            reused = bool(previous and request.options.content_hash_dedup)
            identifier = previous[0] if reused else str(uuid4())
            if not reused:
                db.execute('INSERT INTO training_set_version '
                           '(id,content_hash,created_at,actor,is_frozen,member_count,label_summary,source_note,confirmed_at) '
                           "VALUES (?,?,?,'local',0,?,?,?,NULL)",
                           (identifier, digest, datetime.now(timezone.utc).isoformat(), len(prepared),
                            _json(dict(summary)), request.source_note))
                db.executemany('INSERT INTO training_set_member '
                               '(version_id,cube_id,label_id,annotation_version_id,recipe_version_id,input_fingerprint,n_pixels) '
                               'VALUES (:version_id,:cube_id,:label_id,:annotation_version_id,:recipe_version_id,:input_fingerprint,:n_pixels)',
                               [{**m, 'version_id': identifier} for m in prepared])
            version, members = self._snapshot(db, identifier)
            return {**version, 'version_id': identifier, 'reused': reused,
                    'duplicate_of': previous[0] if previous and not reused else None,
                    **self._resolve(db, identifier, members)}

    def confirm(self, version_id):
        identifier = _identifier(version_id)
        self.registry.recycle.coordinator.check()
        with self.registry.lock, connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            version, _ = self._snapshot(db, identifier)
            if version['is_frozen']:
                raise DataError('TRAINING_SET_IMMUTABLE', '训练集版本已冻结，不可重复确认')
            stamp = datetime.now(timezone.utc).isoformat()
            db.execute('UPDATE training_set_version SET is_frozen=1,confirmed_at=? WHERE id=?', (stamp, identifier))
            return {**version, 'is_frozen': 1, 'confirmed_at': stamp}

    def list_frozen(self):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            return [self._version(db, row[0]) for row in db.execute(
                'SELECT id FROM training_set_version WHERE is_frozen=1 ORDER BY created_at,id')]

    def resolve_members(self, version_id):
        identifier = _identifier(version_id)
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            version, members = self._snapshot(db, identifier)
            if version['is_frozen'] != 1:
                raise DataError('TRAINING_SET_NOT_FROZEN', '须明确指定已冻结的训练集版本')
            return self._resolve(db, identifier, members)
