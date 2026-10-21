"""Regenerate the snapshot from the actual composed app, without changing tests."""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]
from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.app import create_app

app = create_app(AppPaths(ROOT / '.runtime' / ('task06-openapi-' + uuid.uuid4().hex)), EngineIdentity())
(ROOT / 'src-python/spectrumagent/api/openapi.json').write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2)+'\n', 'utf-8')
