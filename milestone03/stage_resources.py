"""Canonical resource staging: preserve the previous ignored stage, compare every byte."""
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / 'artifacts/step2/revision-20261019-m02'
spec = importlib.util.spec_from_file_location('batch', BATCH / 'batch_manifest.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)
manifest = json.loads((BATCH / 'product-manifest.json').read_text(encoding='utf-8'))
source = BATCH / 'staged/backend'
assert batch.inventory(source) == manifest['files']
destination = ROOT / 'src-tauri/resources/backend'
backup = ROOT / '.runtime/m03-prior-resources-backend'
assert destination.resolve().is_relative_to(ROOT) and backup.resolve().is_relative_to(ROOT)
assert not backup.exists(), 'Do not overwrite an unknown prior stage'
if destination.exists():
    destination.rename(backup)
shutil.copytree(source, destination)
assert batch.inventory(destination) == manifest['files']
result = {'timestamp': datetime.now(timezone.utc).isoformat(), 'manifest': str(BATCH / 'product-manifest.json'), 'manifest_sha256': batch.sha(BATCH / 'product-manifest.json'), 'source': str(source), 'destination': str(destination), 'previous_stage_preserved_at': str(backup), 'matched_files': len(manifest['files']), 'bytes': sum(r['bytes'] for r in manifest['files']), 'app': next(r for r in manifest['files'] if r['path']=='app.exe'), 'fault_fixture': False}
output = ROOT / 'milestone03/evidence/P3/resources-staging.json'
with output.open('x',encoding='utf-8') as stream:
    json.dump(result,stream,indent=2)
print(json.dumps(result,indent=2))
