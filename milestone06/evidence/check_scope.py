"""Mechanical whitelist / original semantics guards against the accepted HEAD."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASE = 'a052b3353b2e353acbe4e522d02b7e188c2a05fd'
ALLOWED = {
    'src-python/spectrumagent/api/datasets.py', 'src-python/spectrumagent/api/openapi.json',
    'src-python/spectrumagent/display/falsecolor.py', 'src-python/tests/test_display_falsecolor.py',
    'src-python/tests/data/test_api.py', 'src-tauri/src/datasets_dev.rs',
    'src/components/datasets/api.ts', 'src/components/datasets/types.ts',
    'src/components/annotation/display/DisplayToolbar.tsx', 'src/components/annotation/display/display.ts',
    'src/components/annotation/display/display.test.ts', 'src/components/annotation/canvas/AnnotationCanvas.tsx',
    'src/components/annotation/AnnotationWorkbench.tsx', 'docs/release-notes-v0.1.2.md',
}


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, encoding='utf-8')


def old(path):
    return git('show', BASE+':'+path)


changed = git('diff', '--name-only', BASE).splitlines()
assert all(name in ALLOWED or name.startswith('milestone06/evidence/') for name in changed), changed
dataset_path = 'src-python/spectrumagent/api/datasets.py'
before, after = ast.parse(old(dataset_path)), ast.parse((ROOT/dataset_path).read_text('utf-8'))
def function(tree, name):
    return ast.dump(next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name))
for name in ('png_gray', 'band', 'region', 'region_bounds', 'json_values'):
    assert function(before, name) == function(after, name), name
test = 'src-python/tests/data/test_api.py'
assert (ROOT/test).read_text('utf-8') == old(test).replace(
    'preview = client.get(f"/api/v1/datasets/{identifier}/preview?band=1")',
    'preview = client.get(f"/api/v1/datasets/{identifier}/preview?band=1&stretch=none")')
canvas = 'src/components/annotation/canvas/AnnotationCanvas.tsx'
def load_block(value):
    return value.split('// onload/onerror', 1)[1].split('void Promise.all', 1)[0]
assert load_block(old(canvas)) == load_block((ROOT/canvas).read_text('utf-8'))
rust = 'src-tauri/src/datasets_dev.rs'
def forward(value):
    return value.split('pub fn forward(', 1)[1].split('#[cfg(test)]', 1)[0]
assert forward(old(rust)) == forward((ROOT/rust).read_text('utf-8'))
for path in ('src-python/spectrumagent/annotation/session.py', 'src-python/spectrumagent/api/annotations.py',
             'src-python/spectrumagent/app.py', 'src/components/datasets/DatasetPanel.tsx',
             'package.json', 'package-lock.json', 'requirements-lock.txt', 'src-tauri/Cargo.toml',
             'src-tauri/Cargo.lock', 'src-tauri/src/main.rs', 'milestone03/audit_boundary.py'):
    assert not git('diff', BASE, '--', path), path
result = {'base': BASE, 'product_files': sorted(name for name in changed if name in ALLOWED),
          'whitelist': True, 'png_gray_ast_unchanged': True, 'band_region_ast_unchanged': True,
          'old_python_test_only_authorized_url_change': True, 'png_onload_hotfix_unchanged': True,
          'rust_forward_security_body_unchanged': True, 'annotation_app_s04_dependencies_audit_unchanged': True,
          'seeds_20_sha256': hashlib.sha256((ROOT/'milestone04/evidence/seeds_20.json').read_bytes()).hexdigest(),
          'task_card_sha256_read_only_reference': hashlib.sha256((ROOT/'TASK-06-标注显示能力.md').read_bytes()).hexdigest(),
          'task_card_staged': any(name.startswith('TASK-') for name in git('diff', '--cached', '--name-only').splitlines())}
assert not result['task_card_staged']
assert result['seeds_20_sha256'].upper() == '388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2'
text = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
(Path(__file__).parent/'scope-check.json').write_text(text, 'utf-8')
print(text, end='')
