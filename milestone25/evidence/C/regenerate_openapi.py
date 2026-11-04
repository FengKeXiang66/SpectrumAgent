import json
from pathlib import Path
from backend.paths import AppPaths
from backend.identity import EngineIdentity
from spectrumagent.app import create_app

root = next(parent for parent in Path(__file__).resolve().parents
            if (parent / 'src-python/spectrumagent/app.py').is_file())
app = create_app(AppPaths(root / '.runtime/task25/openapi-c'), EngineIdentity())
target = root / 'src-python/spectrumagent/api/openapi.json'
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('OpenAPI updated; project GET/PUT paths:', '/api/v1/settings/projects/{project_id}/paths' in app.openapi()['paths'])
