"""Source execution uses the same package path as backend.__main__."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src-python'))


@pytest.fixture(autouse=True)
def initialized_storage(tmp_path, monkeypatch):
    from backend.paths import AppPaths
    from spectrumagent.storage import guard
    monkeypatch.setattr(guard, '_guards', {})
    monkeypatch.setattr(guard, '_current', None)
    AppPaths(tmp_path / 'storage-fixture').create_directories()
    yield
    for instance in guard._guards.values():
        instance.close()
