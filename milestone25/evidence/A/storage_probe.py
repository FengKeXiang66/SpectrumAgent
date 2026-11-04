"""A-stage executable counterexamples; creates only new synthetic fixture data.

Run with .venv/Scripts/python.exe milestone25/evidence/A/storage_probe.py.
Artifacts remain in .runtime/task25/storage-probe-* for independent inspection.
"""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import struct
import sys
from uuid import uuid4
import warnings

WORKSPACE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKSPACE / 'src-python'))
sys.path.insert(0, str(WORKSPACE))

from backend.paths import AppPaths
from spectrumagent.api.registry import DatasetRegistry
from spectrumagent.data import DataError
from spectrumagent.storage import guard as storage


def snapshot(directory):
    return [{'path': path.relative_to(directory).as_posix(),
             'sha256': sha256(path.read_bytes()).hexdigest(), 'mtime_ns': path.stat().st_mtime_ns}
            for path in sorted(directory.rglob('*')) if path.is_file()]


def denied(operation, expected):
    try:
        operation()
    except DataError as error:
        assert error.code == expected, error.code
        return error.code
    raise AssertionError('required counterexample was accepted')


def main():
    fixture = WORKSPACE / '.runtime' / 'task25' / ('storage-probe-' + uuid4().hex)
    source = fixture / 'source'
    source.mkdir(parents=True)
    (source / 'original.hdr').write_text(
        'ENVI\nsamples=2\nlines=2\nbands=3\ndata type=12\ninterleave=bip\nbyte order=0\n', encoding='utf-8')
    (source / 'original.img').write_bytes(struct.pack('<12H', *range(12)))
    before = snapshot(source)
    paths = AppPaths(fixture / 'app')
    paths.create_directories()
    registry = DatasetRegistry(paths.database)
    imported = registry.import_path(str(source), raw=True)
    guard = registry.storage_guard
    report = {'fixture': str(fixture), 'imported_id': str(imported.datasets[0].id),
              'startup_order': list(guard.events), 'source_before': before}

    destination = paths.root / 'probe.json'
    storage.resolve_write(destination, kind='WRITE_TEXT').write_text('{}', encoding='utf-8')
    renamed = paths.root / 'renamed.json'
    storage.replace(destination, renamed)
    storage.unlink(renamed)
    report['write_to_source'] = denied(lambda: storage.resolve_write(source / 'must-not-exist.json', kind='WRITE_TEXT'), 'WRITE_TO_SOURCE_DENIED')
    report['delete_from_source'] = denied(lambda: storage.unlink(source / 'original.img'), 'WRITE_TO_SOURCE_DENIED')

    # Inject a newly discovered source inside the whitelist after readiness.
    # This counterexample turns red if the second, source-specific check is removed.
    injected = paths.root / 'newly-discovered-source'
    guard.sources.add(injected)
    report['source_overrides_whitelist'] = denied(lambda: guard.resolve_write(injected / 'blocked.json', kind='WRITE_TEXT'), 'WRITE_TO_SOURCE_DENIED')
    guard.sources.remove(injected)

    calls = []
    original_resolve = guard.resolve_write
    def counted(path, *, kind):
        calls.append(kind)
        return original_resolve(path, kind=kind)
    guard.resolve_write = counted
    guard.resolve_write(paths.root / 'nonrecursive.json', kind='WRITE_TEXT')
    guard.resolve_write = original_resolve
    assert calls == ['WRITE_TEXT']
    report['guard_calls_for_one_audited_resolution'] = len(calls)

    # Holding the business writer cannot block the independent audit writer.
    with closing(sqlite3.connect(paths.database)) as business:
        business.execute('BEGIN IMMEDIATE')
        guard.resolve_write(paths.root / 'during-business-transaction.json', kind='WRITE_TEXT')
        business.rollback()
    report['audit_while_business_writer_locked'] = 'PASS'

    original_check = guard._check_source_overlap
    def failed():
        raise OSError('injected root self-check failure')
    guard._check_source_overlap = failed
    report['injected_selfcheck_failure'] = denied(guard.self_check, 'STORAGE_SELF_CHECK_FAILED')
    report['business_after_failed_selfcheck'] = denied(lambda: guard.resolve_write(paths.root / 'blocked.json', kind='WRITE_TEXT'), 'STORAGE_SELF_CHECK_FAILED')
    guard._check_source_overlap = original_check
    guard.self_check()
    guard.deletion_event('probe', 'PREVIEW', str(imported.datasets[0].id), {'synthetic': True})
    with closing(sqlite3.connect(guard.audit_database)) as db:
        report['audit_decisions'] = dict(db.execute('SELECT decision,count(*) FROM write_audit GROUP BY decision'))
        report['audit_not_null_supply'] = {}
        report['immutable_operations'] = {}
        for table in ('write_audit', 'deletion_audit'):
            columns = db.execute(f'PRAGMA table_info({table})').fetchall()
            assert all(column[3] == 1 and column[4] is None for column in columns)
            report['audit_not_null_supply'][table] = [column[1] for column in columns]
            for action, sql in [('UPDATE', f'UPDATE {table} SET action=action'), ('DELETE', f'DELETE FROM {table}')]:
                try:
                    db.execute(sql)
                except sqlite3.IntegrityError as error:
                    assert str(error) == 'APPEND_ONLY_AUDIT'
                    report['immutable_operations'][table + '.' + action] = str(error)
                else:
                    raise AssertionError('audit mutation succeeded')
    after = snapshot(source)
    assert after == before
    report['source_after'] = after
    report['source_unchanged'] = True
    guard.close()

    buffered_root = fixture / 'buffered-app'
    (buffered_root / 'db').mkdir(parents=True)
    buffered = storage.WriteGuard(buffered_root, buffer_limit=2)
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always')
        for _ in range(3):
            denied(lambda: buffered.resolve_write(buffered_root / 'blocked.json', kind='WRITE_TEXT'), 'STORAGE_SELF_CHECK_FAILED')
    assert len(buffered.buffer) == 2
    assert [str(warning.message) for warning in captured] == ['AUDIT_BUFFER_OVERFLOW']
    buffered.attach_database()
    with closing(sqlite3.connect(buffered.audit_database)) as db:
        flushed = db.execute("SELECT count(*) FROM write_audit WHERE flushed_at<>''").fetchone()[0]
        overflow_alert = db.execute("SELECT action,reason FROM write_audit WHERE action='AUDIT_BUFFER_OVERFLOW'").fetchall()
    assert flushed == 2 and not buffered.buffer
    assert overflow_alert == [('AUDIT_BUFFER_OVERFLOW', 'EVICTED_RECORDS:1')]
    report['bounded_buffer'] = {'capacity': 2, 'overflow_count': buffered.overflow_count,
                                'warnings': [str(warning.message) for warning in captured], 'flushed_rows': flushed,
                                'persistent_alert': overflow_alert}
    buffered.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
