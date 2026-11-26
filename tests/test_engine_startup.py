"""The ready-to-serve application must not eagerly load the science stack."""
import os
from pathlib import Path
import subprocess
import sys


def test_startup_and_health_have_no_heavy_algorithm_imports(tmp_path):
    root = Path(__file__).resolve().parents[1]
    check = """
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app

paths = AppPaths(Path(sys.argv[1]))
paths.create_directories(activate_output=True)
identity = EngineIdentity()
with TestClient(create_app(paths, identity)) as client:
    assert client.get('/health').json()['boot_id'] == identity.boot_id
    assert not any(paths.testdata.iterdir())
    unexpected = {'sklearn', 'scipy', 'skimage', 'matplotlib'} & sys.modules.keys()
    assert not unexpected, unexpected
    response = client.get('/smoke', headers={'Authorization': 'Bearer ' + identity.token})
    assert response.status_code == 200 and response.json()['bands'] == 8, response.text
"""
    result = subprocess.run(
        [sys.executable, '-B', '-c', check, str(tmp_path)],
        cwd=root,
        env={**os.environ, 'PYTHONPATH': str(root / 'src-python'),
             'SPECTRUMAGENT_DATA_ROOT': str(tmp_path), 'SPECTRUMAGENT_PERMANENT_ROOT': str(tmp_path)},
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
