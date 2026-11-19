"""Content-only batch identity; preprocessing references belong to training snapshots."""
from datetime import datetime, timezone
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import UUID, uuid4

import numpy as np

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.preprocess.run import file_sha256


def cube_content_hash(header_hash, data_hash):
    return sha256((header_hash + '|' + data_hash).encode('ascii')).hexdigest()


def batch_content_hash(cube_hashes):
    return sha256('|'.join(sorted(cube_hashes)).encode('ascii')).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class DatasetVersions:
    def __init__(self, registry, *, preview_image=None):
        self.registry, self.database = registry, registry.database
        self.preview_image = preview_image

    def get_frozen(self, version_id):
        """Read the explicit version and its actual members in one read snapshot.

        mode=ro also permits evidence inspection without bootstrapping/migrating a
        user's database. Hash deduplication never substitutes a different version.
        """
        try:
            identifier = str(UUID(str(version_id)))
        except (ValueError, TypeError, AttributeError):
            raise DataError('INVALID_DATASET_VERSION', '请明确指定合法的数据集版本引用') from None
        with closing(sqlite3.connect(Path(self.database).resolve().as_uri() + '?mode=ro', uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            row = db.execute('SELECT id,is_frozen,content_hash,cube_count FROM dataset_version WHERE id=?',
                             (identifier,)).fetchone()
            if row is None or row['is_frozen'] != 1:
                raise DataError('DATASET_VERSION_NOT_FROZEN', '版本不存在或尚未确认冻结')
            members = [dict(item) for item in db.execute(
                'SELECT cube_id,content_hash FROM dataset_version_item WHERE version_id=? ORDER BY cube_id',
                (identifier,))]
            if not members or len(members) != row['cube_count']:
                raise DataError('DATASET_VERSION_INCONSISTENT', '版本成员数量不完整，已停止准备')
            try:
                valid = all(str(UUID(m['cube_id'])) == m['cube_id'] and len(m['content_hash']) == 64
                            and all(c in '0123456789abcdef' for c in m['content_hash']) for m in members)
            except (ValueError, TypeError, AttributeError):
                valid = False
            if not valid or batch_content_hash(m['content_hash'] for m in members) != row['content_hash']:
                raise DataError('DATASET_VERSION_INCONSISTENT', '版本成员身份不完整，已停止准备')
            return {**dict(row), 'members': members}

    def _inspect(self, cube_ids, *, downsample):
        items, prepared, failures = [], [], []
        for cube_id in cube_ids:
            report = {'path': None, 'status': '阻断', 'wavelength_axis': [],
                      'bit_depth': None, 'bytes': None, 'warnings': []}
            try:
                stored, _ = self.registry.get(cube_id)
                report['path'] = stored.header_path
                dataset, _ = self.registry.readable(cube_id)
                header, data = Path(dataset.header_path), Path(dataset.data_path)
                digest = cube_content_hash(file_sha256(header), file_sha256(data))
                warnings = [] if dataset.wavelengths else ['未提供波长轴；不推测波长刻度']
                report.update(status='告警' if warnings else '通过', wavelength_axis=dataset.wavelengths,
                              bit_depth=np.dtype(dataset.dtype).itemsize * 8,
                              bytes=header.stat().st_size + data.stat().st_size, warnings=warnings)
                if downsample and self.preview_image is not None:
                    self.preview_image(cube_id, band=0, size='preview', stretch='auto', bands=None)
                prepared.append((cube_id, digest, dataset.metadata, str(header.parent)))
            except (DataError, OSError) as error:
                if isinstance(error, OSError):
                    error = DataError('READ_FAILED', '版本报告源文件读取失败', reason=type(error).__name__)
                report['status'] = '阻断'
                failures.append({'cube_id': cube_id, **error.as_dict()})
            items.append(report)
        return items, prepared, failures

    def preview(self, cube_ids, options=None):
        self.registry.recycle.coordinator.check()
        if not cube_ids or len(set(cube_ids)) != len(cube_ids):
            raise DataError('INVALID_REQUEST', '版本须包含非空且不重复的数据集引用', cube_ids=cube_ids)
        options = options or {}
        items, prepared, failures = self._inspect(cube_ids, downsample=options.get('preview_downsample', True))
        if failures:
            raise DataError('IMPORT_BATCH_INVALID', '整批版本未登记；请修复所有无效项', items=items, failures=failures)
        content_hash = batch_content_hash(row[1] for row in prepared)
        with self.registry.lock, connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT id FROM dataset_version WHERE content_hash=? ORDER BY created_at,id LIMIT 1',
                                  (content_hash,)).fetchone()
            reused = bool(previous and options.get('content_hash_dedup', True))
            identifier = previous[0] if reused else str(uuid4())
            if not reused:
                db.execute('INSERT INTO dataset_version '
                           '(id,content_hash,created_at,actor,is_frozen,cube_count,source_root,acq_meta,confirmed_at,note) '
                           'VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (identifier, content_hash, datetime.now(timezone.utc).isoformat(), 'local', 0, len(prepared),
                            _json(sorted({row[3] for row in prepared})),
                            _json({row[0]: row[2] for row in prepared}), None, None))
                db.executemany('INSERT INTO dataset_version_item '
                               '(version_id,cube_id,content_hash,acq_meta) VALUES (?,?,?,?)',
                               [(identifier, cube, digest, _json(meta))
                                for cube, digest, meta, _ in prepared])
        return {'version_id': identifier, 'reused': reused,
                'duplicate_of': previous[0] if previous and not reused else None,
                'cube_count': len(prepared), 'content_hash': content_hash, 'items': items,
                'warnings': [warning for item in items for warning in item['warnings']], 'blocked': False}

    @staticmethod
    def _version(db, identifier):
        row = db.execute('SELECT * FROM dataset_version WHERE id=?', (str(identifier),)).fetchone()
        if row is None:
            raise DataError('INVALID_REQUEST', '数据集版本不存在', version_id=str(identifier))
        return dict(row)

    def confirm(self, version_id):
        self.registry.recycle.coordinator.check()
        with self.registry.lock, connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE')
            version = self._version(db, version_id)
            if version['is_frozen']:
                raise DataError('INVALID_REQUEST', '版本已冻结，不可重复确认', version_id=str(version_id))
            confirmed_at = datetime.now(timezone.utc).isoformat()
            db.execute('UPDATE dataset_version SET is_frozen=1,confirmed_at=? WHERE id=?', (confirmed_at, str(version_id)))
            cube_ids = sorted(row[0] for row in db.execute(
                'SELECT cube_id FROM dataset_version_item WHERE version_id=?', (str(version_id),)))
        return {'dataset_version_id': str(version_id), 'cube_ids': cube_ids,
                'content_hash': version['content_hash'], 'created_at': version['created_at'], 'actor': version['actor'],
                'is_frozen': 1, 'confirmed_at': confirmed_at, 'reused': False}

    def list_frozen(self):
        with connect_database(self.database) as db:
            db.row_factory = sqlite3.Row
            db.execute('BEGIN')
            versions = [dict(row) for row in db.execute(
                'SELECT id,content_hash,cube_count,created_at,confirmed_at,is_frozen '
                'FROM dataset_version WHERE is_frozen=1 ORDER BY created_at,id')]
            for version in versions:
                version['cube_ids'] = sorted(row[0] for row in db.execute(
                    'SELECT cube_id FROM dataset_version_item WHERE version_id=?', (version['id'],)))
            return versions
