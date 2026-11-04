from pathlib import Path
import sys
import tempfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'fixtures'))


@pytest.fixture(autouse=True)
def isolated_storage_policy(tmp_path, monkeypatch):
    """Keep synthetic sources, application data and system temp as separate roots.

    The application still enforces every source-overlap rule. A private system
    temp directory avoids declaring pytest's entire source fixture tree writable.
    """
    from spectrumagent.storage import guard
    temporary = tmp_path.parent / (tmp_path.name + '-system-temp')
    temporary.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(temporary))
    monkeypatch.setattr(guard, '_guards', {})
    monkeypatch.setattr(guard, '_current', None)
    yield
    for instance in guard._guards.values():
        instance.close()
