"""A-stage counterexamples: each assertion checks a broken boundary or lifecycle."""
from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest

from backend.paths import AppPaths
from spectrumagent.data import DataError
from spectrumagent.storage import guard as module
from spectrumagent.storage.guard import WriteGuard


@pytest.fixture
def case(tmp_path):
    root, output, temporary, source = [tmp_path / name for name in ('app', 'output', 'temporary', 'source')]
    for path in (root / 'trash', root / 'db', output, temporary, source):
        path.mkdir(parents=True)
    (source / 'input.hdr').write_text('original source', encoding='utf-8')
    guard = WriteGuard(root, output_root=output, temp_root=temporary, source_roots=[source])
    guard.self_check()
    yield guard, source
    guard.close()


def rows(guard):
    with sqlite3.connect(guard.audit_database) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute('SELECT * FROM write_audit ORDER BY rowid')]


def test_three_roots_allow_but_source_write_delete_and_parent_delete_deny(case):
    """Red if a root is omitted, a source mutation is accepted or DENY is unaudited."""
    guard, source = case
    original = source / 'input.hdr'
    before = [(p.name, sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in source.iterdir()]
    for root in guard.roots:
        assert guard.resolve_write(root / 'new.json', kind='JSON') == root / 'new.json'
    for operation in (lambda: guard.resolve_write(original, kind='JSON'),
                      lambda: guard.resolve_delete(original),
                      lambda: guard.resolve_delete(source.parent)):
        with pytest.raises(DataError) as caught:
            operation()
        assert caught.value.code == 'WRITE_TO_SOURCE_DENIED'
    after = [(p.name, sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in source.iterdir()]
    assert after == before
    denied = [row for row in rows(guard) if row['decision'] == 'DENY']
    assert len(denied) == 3
    assert {row['reason'] for row in denied} == {'WRITE_TO_SOURCE_DENIED'}
    assert all(row['actor'] == 'local' and row['deletion_id'] == '' for row in denied)


def test_normalization_and_symlink_cannot_escape(case, tmp_path):
    """Red if .. normalization or a symlink changes the authorization target."""
    guard, source = case
    escape = guard.root / '..' / 'source' / 'input.hdr'
    with pytest.raises(DataError, match='目标路径'):
        guard.resolve_write(escape, kind='JSON')
    link = guard.root / 'link'
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError:
        # Windows installations without symlink privilege still exercise .. above.
        assert rows(guard)[-1]['decision'] == 'DENY'
    else:
        with pytest.raises(DataError):
            guard.resolve_delete(link / 'input.hdr')
        assert rows(guard)[-1]['target_path'] == str((source / 'input.hdr').resolve())


def test_audit_insert_is_independent_and_nonrecursive(case, monkeypatch):
    """Red if audit INSERT calls the guarded database/write channel recursively."""
    guard, _ = case
    calls = []
    original = guard.resolve_write
    def counted(path, *, kind):
        calls.append((path, kind))
        return original(path, kind=kind)
    monkeypatch.setattr(guard, 'resolve_write', counted)
    guard.resolve_write(guard.root / 'one.json', kind='JSON')
    assert len(calls) == 1
    assert rows(guard)[-1]['action'] == 'JSON'


@pytest.mark.parametrize('table', ['write_audit', 'deletion_audit'])
@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE'])
def test_audits_are_append_only_and_not_default_filled(case, table, operation):
    """Red if raw SQL can mutate audit rows or NOT NULL values rely on DEFAULT."""
    guard, _ = case
    guard.deletion_event('batch', 'PREVIEW', 'cube', {'versions': 0})
    with sqlite3.connect(guard.audit_database) as db:
        columns = list(db.execute(f'PRAGMA table_info({table})'))
        assert all(column[4] is None for column in columns)
        assert all(column[3] == 1 for column in columns)
        statement = f'UPDATE {table} SET action=action' if operation == 'UPDATE' else f'DELETE FROM {table}'
        with pytest.raises(sqlite3.IntegrityError, match='APPEND_ONLY_AUDIT'):
            db.execute(statement)
        assert db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] > 0


def test_bounded_buffer_warns_and_flushes_without_reentering_guard(tmp_path, monkeypatch):
    """Red if startup buffering grows without bound, overflows silently or loses flush timestamps."""
    root = tmp_path / 'app'
    (root / 'db').mkdir(parents=True)
    guard = WriteGuard(root, buffer_limit=2)
    for _ in range(2):
        with pytest.raises(DataError):
            guard.resolve_write(root / 'blocked', kind='JSON')
    with pytest.warns(RuntimeWarning, match='AUDIT_BUFFER_OVERFLOW'):
        with pytest.raises(DataError):
            guard.resolve_delete(root / 'blocked')
    assert len(guard.buffer) == 2 and guard.overflow_count == 1
    def recursive(*args, **kwargs):
        pytest.fail('audit flush re-entered resolve_write')
    monkeypatch.setattr(guard, 'resolve_write', recursive)
    guard.attach_database()
    assert not guard.buffer
    persisted = rows(guard)
    assert len(persisted) == 3
    assert sum(bool(row['flushed_at']) for row in persisted) == 2
    assert persisted[-1]['action'] == 'AUDIT_BUFFER_OVERFLOW'
    assert persisted[-1]['reason'] == 'EVICTED_RECORDS:1'
    guard.close()


def test_selfcheck_failure_keeps_business_writes_closed(case, monkeypatch):
    """Red if a failed root self-check leaves a previously-ready guard writable."""
    guard, _ = case
    def failed():
        raise OSError('injected root failure')
    monkeypatch.setattr(guard, '_check_source_overlap', failed)
    with pytest.raises(DataError) as error:
        guard.self_check()
    assert error.value.code == 'STORAGE_SELF_CHECK_FAILED'
    with pytest.raises(DataError):
        guard.resolve_write(guard.root / 'forbidden.json', kind='JSON')
    assert rows(guard)[-1]['decision'] == 'DENY'


def test_bootstrap_creates_trash_then_selfchecks_then_allows(tmp_path, monkeypatch):
    """Red if readiness is published before trash creation or before the self-check."""
    paths = AppPaths(tmp_path / 'app')
    checked = []
    original = WriteGuard.self_check
    def observed(guard):
        assert paths.trash.is_dir()
        assert not guard.ready
        checked.append('trash_before_self_check')
        return original(guard)
    monkeypatch.setattr(WriteGuard, 'self_check', observed)
    paths.create_directories()
    guard = module.for_database(paths.database)
    assert paths.trash.is_dir()
    assert guard.events == ['directories_created', 'self_check', 'business_ready']
    assert guard.ready
    assert checked == ['trash_before_self_check']


def test_known_source_overlap_blocks_bootstrap_without_source_mutation(tmp_path):
    """Red if bootstrap mkdir modifies a previously registered source tree."""
    root = tmp_path / 'app'
    guard = WriteGuard(root, source_roots=[tmp_path])
    module._guards[root.resolve()] = guard
    before = sorted(str(path) for path in tmp_path.rglob('*'))
    with pytest.raises(DataError):
        AppPaths(root).create_directories()
    assert sorted(str(path) for path in tmp_path.rglob('*')) == before


def test_audit_failure_denies_the_file_mutation(case, monkeypatch):
    """Red if an audit database outage permits a formerly-ready business write."""
    guard, _ = case
    def failed(*args, **kwargs):
        raise sqlite3.OperationalError('injected audit failure')
    monkeypatch.setattr(guard, '_insert', failed)
    with pytest.raises(DataError) as error:
        guard.resolve_write(guard.root / 'unlogged.json', kind='JSON')
    assert error.value.code == 'STORAGE_SELF_CHECK_FAILED'
    assert not guard.ready and len(guard.buffer) == 1


def test_insert_or_replace_cannot_rewrite_an_existing_audit(case):
    """Red if SQLite's REPLACE path bypasses the UPDATE/DELETE audit triggers."""
    guard, _ = case
    original = rows(guard)[0]
    with sqlite3.connect(guard.audit_database) as db:
        with pytest.raises(sqlite3.IntegrityError, match='APPEND_ONLY_AUDIT'):
            db.execute('INSERT OR REPLACE INTO write_audit VALUES (?,?,?,?,?,?,?,?,?)', tuple(original.values()))
    assert rows(guard)[0] == original


def test_audit_channel_reuses_one_connection_and_closes(case):
    """Red if audit INSERT leaks connections or leaves an open writer at shutdown."""
    guard, _ = case
    connection = guard._audit_connection
    guard.resolve_write(guard.root / 'one', kind='JSON')
    guard.resolve_write(guard.root / 'two', kind='JSON')
    assert guard._audit_connection is connection
    guard.close()
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')


def test_independent_audit_channel_cannot_write_outside_its_fixed_root(case):
    """Red if the recursion exemption permits an audit file in a source directory."""
    guard, source = case
    before = [(p.name, p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir()]
    guard.audit_database = source / 'must-not-be-created.sqlite3'
    with pytest.raises(DataError) as caught:
        guard.resolve_write(guard.root / 'business.json', kind='JSON')
    assert caught.value.code == 'STORAGE_SELF_CHECK_FAILED'
    assert [(p.name, p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir()] == before
    assert guard.buffer[-1][4:6] == ('DENY', 'WRITE_AUDIT_UNAVAILABLE')


def test_source_inventory_is_reloaded_on_fresh_guard(tmp_path, monkeypatch):
    """Red if a fresh process forgets previously registered source directories."""
    paths = AppPaths(tmp_path / 'app')
    source = tmp_path / 'source'
    source.mkdir()
    paths.create_directories()
    original = module.for_database(paths.database)
    original.add_sources([source])
    original.close()
    monkeypatch.setattr(module, '_guards', {})
    monkeypatch.setattr(module, '_current', None)
    paths.create_directories()
    restarted = module.for_database(paths.database)
    assert source.resolve() in restarted.sources
    with pytest.raises(DataError) as denied:
        restarted.resolve_delete(source / 'untouched.hdr')
    assert denied.value.code == 'WRITE_TO_SOURCE_DENIED'


def test_configured_output_root_is_checked_before_becoming_writable(tmp_path):
    """Red if cached bootstrap state ignores an explicitly configured output root."""
    paths = AppPaths(tmp_path / 'app')
    paths.create_directories()
    output = tmp_path / 'output'
    output.mkdir()
    guard = module.for_database(paths.database)
    with pytest.raises(DataError) as denied:
        guard.resolve_write(output / 'before.json', kind='JSON')
    assert denied.value.code == 'WRITE_TO_SOURCE_DENIED'
    configured = module.initialize(paths, output_root=output)
    assert configured is guard and configured.ready
    assert configured.resolve_write(output / 'after.json', kind='JSON') == output / 'after.json'
