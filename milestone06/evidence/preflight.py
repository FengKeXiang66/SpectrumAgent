"""Read-only source-data checks for TASK-06 contract conflicts; no feature implementation."""
import base64
import hashlib
import json
import math
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src-python')]

import numpy as np

from spectrumagent.api.datasets import png_gray
from spectrumagent.api.registry import DatasetRegistry

runtime = ROOT / '.runtime' / ('task06-preflight-' + uuid.uuid4().hex)
registry = DatasetRegistry(runtime / 'registry.sqlite')
header = (ROOT / 'milestone04/evidence/calibration/cubes_11.txt').read_text('utf-8').splitlines()[0]
record = registry.import_path(header).datasets[0]
ds, _ = registry.readable(record.id, raw=False)
stride = max(1, math.ceil(max(ds.shape[:2]) / 512))
image = ds.read_subimage(list(range(0, ds.shape[0], stride)),
                         list(range(0, ds.shape[1], stride)), [0])[:, :, 0]
assert np.isfinite(image).all()
mapped = np.clip((image - image.min()) / (image.max() - image.min()) * 255, 0, 255)
head = mapped.astype(np.uint8)
rounded = np.rint(mapped).astype(np.uint8)
old_png, round_png = map(png_gray, (head, rounded))
example = [186, 124, 62]  # Literal from acceptance/performance cases, not an algorithm choice.
result = {
    'head': 'a052b3353b2e353acbe4e522d02b7e188c2a05fd',
    'mode': 'repository root .venv/Scripts/python.exe milestone06/evidence/preflight.py; sandbox default; project Registry.readable(raw=False), no manual memmap; isolated E runtime',
    'source_header': header,
    'cube_shape': list(ds.shape),
    'preview_shape': list(image.shape),
    'stride': stride,
    'round_vs_head_different_pixels': int(np.count_nonzero(head != rounded)),
    'head_png_sha256': hashlib.sha256(base64.b64decode(old_png)).hexdigest(),
    'round_png_sha256': hashlib.sha256(base64.b64decode(round_png)).hexdigest(),
    'png_bytes_equal': old_png == round_png,
    'card_explicit_bands_example': example,
    'example_satisfies_strict_increasing': all(a < b for a, b in zip(example, example[1:])),
    'whitelist_gaps': [
        'src-python/spectrumagent/api/openapi.json (existing full snapshot equality assertion)',
        'src-python/tests/data/test_api.py:132 (existing default-preview test asserts min/max truncation)',
        'src/components/annotation/display/display.ts (named by card 6.9, absent from 4)',
        'docs/release-notes-v0.1.2.md (required by card 2.1, absent from 4)',
    ],
    'pytest_cargo_node_baselines': 'not run in this preflight; blocked by contract conflicts',
}
assert not result['png_bytes_equal'] and result['round_vs_head_different_pixels'] > 0
assert not result['example_satisfies_strict_increasing']
text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
(Path(__file__).parent / 'preflight-output.json').write_text(text, 'utf-8')
print(text, end='')
