"""Long-lived daily logs are authorized once per file and retain write boundaries."""
from contextlib import closing
from datetime import datetime
import logging
import sqlite3
import sys

import pytest

from test_experiments import workspace
from backend import logging_config
from spectrumagent.data import DataError
from spectrumagent.storage import guard


def test_daily_log_audits_open_and_rollover_without_per_record_transactions(workspace, tmp_path, monkeypatch):
    storage = guard.for_database(workspace.database)
    source = tmp_path / 'protected'
    source.mkdir()
    storage.add_sources([source])
    class Clock:
        day = 24

        @classmethod
        def now(cls):
            return datetime(2026, 11, cls.day)

    monkeypatch.setattr(logging_config, 'datetime', Clock)
    handler = logging_config.DailyJsonFile(workspace.logs)
    errors = []
    monkeypatch.setattr(handler, 'handleError', lambda record: errors.append(sys.exc_info()[1]))
    record = logging.LogRecord('test', logging.INFO, __file__, 1, 'daily event', (), None)
    try:
        for _ in range(12):
            handler.handle(record)
        Clock.day = 25
        for _ in range(4):
            handler.handle(record)
        Clock.day = 26
        handler.directory = source
        handler.handle(record)
    finally:
        handler.close()

    assert len((workspace.logs / 'engine-20261124.jsonl').read_text('utf8').splitlines()) == 12
    assert len((workspace.logs / 'engine-20261125.jsonl').read_text('utf8').splitlines()) == 4
    assert not (source / 'engine-20261126.jsonl').exists()
    assert len(errors) == 1 and errors[0].code == 'WRITE_TO_SOURCE_DENIED'
    with closing(sqlite3.connect(storage.audit_database)) as db:
        opens = db.execute("SELECT decision FROM write_audit WHERE action='FILE_OPEN' AND target_path LIKE '%engine-%'").fetchall()
        assert opens == [('ALLOW',), ('ALLOW',), ('DENY',)]
        assert db.execute("SELECT count(*) FROM write_audit WHERE action='LOG_APPEND'").fetchone()[0] == 0


def test_source_index_keeps_ancestor_and_descendant_write_guards(workspace):
    directory = workspace.root / 'inputs' / 'protected'
    file = workspace.root / 'registered' / 'input.img'
    storage = guard.WriteGuard(workspace.root, source_roots=[directory,file])
    try:
        storage.attach_database()
        # A transient overlap during startup must still protect all registered paths.
        for target, deleting in ((directory,False), (directory/'child.json',False), (file,False),
                                 (directory.parent,True), (file.parent,True)):
            with pytest.raises(DataError) as caught:
                storage._resolve(target, 'TEST_WRITE', startup=True, deleting=deleting)
            assert caught.value.code == 'WRITE_TO_SOURCE_DENIED'
        sibling = file.with_name('output.img')
        assert storage._resolve(sibling, 'TEST_WRITE', startup=True, deleting=True) == sibling.resolve()
    finally:
        storage.close()

    live = guard.for_database(workspace.database)
    with pytest.raises(DataError):
        live.add_sources([workspace.logs / 'bad-source'])
    assert live.resolve_write(workspace.logs / 'bad-source', kind='TEST_WRITE')
