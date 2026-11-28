"""Atomic rename tolerates a brief Windows denial without hiding real failures."""
import os
from types import SimpleNamespace

import pytest

from test_experiments import workspace
from spectrumagent.data import DataError
from spectrumagent.storage import guard


def windows_error(code):
    error = OSError('simulated Windows rename denial')
    error.winerror = code
    return error


@pytest.mark.parametrize('code', [5, 32, 33])
def test_transient_windows_denial_retries_same_atomic_move(workspace, monkeypatch, code):
    source, destination = workspace.snapshots/'source', workspace.snapshots/'destination'
    guard.mkdir(source, parents=True)
    (source/'closed.txt').write_text('preserved', encoding='utf8')
    original = os.replace
    calls, waits = [], []
    def replace(a, b):
        calls.append((a, b))
        if len(calls) == 1:
            raise windows_error(code)
        return original(a, b)
    monkeypatch.setattr(guard, 'os', SimpleNamespace(name='nt', replace=replace))
    monkeypatch.setattr(guard, 'sleep', waits.append)
    guard.replace(source, destination)
    assert len(calls) == 2 and calls[0] == calls[1] and waits == [.1]
    assert not source.exists() and (destination/'closed.txt').read_text('utf8') == 'preserved'


@pytest.mark.parametrize('platform,code,attempts', [('nt',5,2), ('nt',2,1), ('posix',5,1)])
def test_persistent_or_unrelated_errors_remain_errors(workspace, monkeypatch, platform, code, attempts):
    source, destination = workspace.snapshots/'source', workspace.snapshots/'destination'
    guard.mkdir(source, parents=True)
    calls, waits = [], []
    failure = windows_error(code)
    def replace(a, b):
        calls.append((a, b))
        raise failure
    monkeypatch.setattr(guard, 'os', SimpleNamespace(name=platform, replace=replace))
    monkeypatch.setattr(guard, 'sleep', waits.append)
    with pytest.raises(OSError) as caught:
        guard.replace(source, destination)
    assert caught.value is failure and len(calls) == attempts
    assert waits == ([.1] if attempts == 2 else [])
    assert source.exists() and not destination.exists()


def test_retry_rechecks_write_authorization(workspace, monkeypatch):
    source, destination = workspace.snapshots/'source', workspace.snapshots/'destination'
    guard.mkdir(source, parents=True)
    original = guard.resolve_write
    checks, calls = [], []
    def checked(path, *, kind):
        checks.append(path)
        if len(checks) == 2:
            raise DataError('WRITE_TO_SOURCE_DENIED', 'Authorization changed')
        return original(path, kind=kind)
    def replace(a, b):
        calls.append((a, b))
        raise windows_error(5)
    monkeypatch.setattr(guard, 'resolve_write', checked)
    monkeypatch.setattr(guard, 'os', SimpleNamespace(name='nt', replace=replace))
    monkeypatch.setattr(guard, 'sleep', lambda seconds: None)
    with pytest.raises(DataError) as caught:
        guard.replace(source, destination)
    assert caught.value.code == 'WRITE_TO_SOURCE_DENIED'
    assert len(checks) == 2 and len(calls) == 1
    assert source.exists() and not destination.exists()
