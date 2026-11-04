"""Replay the resolved active-B/recycled-A case against a fresh synthetic DB."""
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4

root = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(root), str(root/'src-python'), str(root/'src-python/tests/fixtures')]
from spectrumagent.storage import guard as storage

spec = importlib.util.spec_from_file_location('fixture', root/'src-python/tests/storage/test_recycle.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
base = root/'.runtime/task25'/('reimport-resolved-'+uuid4().hex[:8])
base.mkdir(parents=True)
c = module.case.__wrapped__(base/'fixture')
preview = c.store.preview(c.cube)
c.store.delete(c.cube, confirm=True, preview_token=preview['preview_token'])
fresh = c.registry.import_path(str(c.header), raw=True, confirm_new=True).datasets[0]
normal = c.registry.import_path(str(c.header), raw=True)
confirmed = c.registry.import_path(str(c.header), raw=True, confirm_new=True)
for result in (normal, confirmed):
    assert result.datasets[0].id == fresh.id and result.datasets[0].existing is True
    assert result.summary.model_dump() == {'total': 1, 'imported': 0, 'existing': 1}
print(json.dumps({'authority':'eb1b25b', 'mode':'fresh synthetic ENVI / real SQLite / storage guard',
                  'old_id':c.cube,'active_id':str(fresh.id),
                  'without_confirm_new':{'id':str(normal.datasets[0].id),'existing':normal.datasets[0].existing,
                                         'summary':normal.summary.model_dump()},
                  'with_confirm_new':{'id':str(confirmed.datasets[0].id),'existing':confirmed.datasets[0].existing,
                                      'summary':confirmed.summary.model_dump()}},indent=2))
for guard in storage._guards.values():
    guard.close()
