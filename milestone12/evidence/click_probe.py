import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path('E:/AI_Agent')
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

fixtures = module('task12_fixtures', 'src-python/tests/annotation/conftest.py')
routes = module('task12_routes', 'src-python/tests/annotation/test_routes.py')
out = ROOT / '.runtime/task12' / sys.argv[1]
out.mkdir(parents=True, exist_ok=False)
case = fixtures.annotation_case.__wrapped__(out)
context = routes.http_annotation.__wrapped__(case)
h = next(context)
try:
    routes.segment(h)
    counts = {'POST /regions': 0, 'GET /working': 0, 'png_base64': 0, 'segments_png': 0}
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('png_base64', 'segments_png'):
                    counts[key] += 1
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    for index in range(100):
        response = routes.region(h, geometry={'superpixels': [index % (int(routes.state(h).segments.max()) + 1)]})
        assert response.status_code == 200, response.text
        counts['POST /regions'] += 1
        collect(response.json())
        response = h.client.get(h.base + '/annotations/working')
        assert response.status_code == 200, response.text
        counts['GET /working'] += 1
        collect(response.json())
    (out / 'counts.json').write_text(json.dumps(counts, indent=2), 'utf-8')
    print(json.dumps(counts))
finally:
    try:
        next(context)
    except StopIteration:
        pass
