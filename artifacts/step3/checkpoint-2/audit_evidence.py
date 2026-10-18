"""Read-only replay of original log segments; uses the launch EOFs and closed end offsets."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

out = Path(sys.argv[1]).resolve()
data = Path(os.environ['LOCALAPPDATA']) / 'SpectrumAgent/logs'
receipt = json.loads((out / 'receipt.json').read_text(encoding='utf-8'))
checks = []
ends = {}
for meta in sorted(out.glob('*.launch.json')):
    baseline = json.loads(meta.read_text(encoding='utf-8'))['log_baseline_offsets']
    case = meta.name.removesuffix('.launch.json')
    for log in list(out.glob(case + '.final.engine-*.jsonl')) + list(out.glob(case + '.final.shell-*.log')):
        name = log.name.removeprefix(case + '.final.')
        content = log.read_bytes()
        source = (data / name).read_bytes()
        offset = baseline.get(name, 0)
        exact = source[offset:offset + len(content)] == content
        checks.append(dict(case=case, log=name, baseline=offset, bytes=len(content), exact_original_segment=exact))
        assert exact, (case, name)
        ends[name] = max(ends.get(name, 0), offset + len(content))
base = json.loads((out / 'dev-ready.launch.json').read_text(encoding='utf-8'))['log_baseline_offsets']
source_checks = {}
sample = []
codes = []
for name, expected in receipt['original_runtime_append_sha256'].items():
    raw = (data / name).read_bytes()[base.get(name, 0):ends[name]]
    actual = hashlib.sha256(raw).hexdigest()
    assert actual == expected, name
    rows = [json.loads(line) for line in raw.splitlines()]
    source_checks[name] = dict(
        start=base.get(name, 0), end=ends[name], bytes=len(raw), lines=len(rows), sha256=actual,
        receipt_match=True,
        hex32_token_pattern_count=len(re.findall(rb'(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])', raw)),
        literal_token_key_count=raw.count(b'"token"'))
    if name.startswith('engine-'):
        sample = [line for line in raw.splitlines(keepends=True) if json.loads(line).get('boot_id')][:3]
    else:
        codes = [row.get('exit_code') for row in rows if row.get('event') == 'engine_process_exit']
        assert 70 not in codes
(out / 'log-samples.jsonl').write_bytes(b''.join(sample))
result = dict(exact_original_segments=checks, original_increment_checks=source_checks, observed_engine_exit_codes=codes)
destination = out / 'independent-original-log-audit.json'
assert not destination.exists(), 'refusing to overwrite previous audit'
destination.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='')
print(json.dumps(dict(exact_original_segment_count=len(checks), all_exact=True,
                     original_increment_checks=source_checks, observed_engine_exit_codes=codes), indent=2))
