"""Copy the approved existing toolchain to E:; never overwrite unknown content."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime

ROOT = Path(r'E:\AI_Agent')
OUT = Path(__file__).resolve().parent
NODE = Path(r'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
NPM = Path(r'D:\Install\nvm\nodejs')
TARGET = ROOT / '.toolchains/node24.19.0-npm10.8.2'
EXPECTED_NODE_SHA = '3602f2bb1a10f2cbab4c36886218a33c1ab3db87290e73b033c46c77147d0237'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert sha(NODE) == EXPECTED_NODE_SHA, 'source Node differs from approved fingerprint'
    assert json.loads((NPM / 'node_modules/npm/package.json').read_text(encoding='utf-8'))['version'] == '10.8.2'
    sources = {'node.exe': NODE, 'npm.cmd': NPM / 'npm.cmd', 'npx.cmd': NPM / 'npx.cmd'}
    sources.update({p.relative_to(NPM).as_posix(): p for p in (NPM / 'node_modules/npm').rglob('*') if p.is_file()})
    before = {name: {'bytes': path.stat().st_size, 'sha256': sha(path)} for name, path in sources.items()}
    mode = 'reuse' if TARGET.exists() else 'copy'
    if TARGET.exists():
        existing = {p.relative_to(TARGET).as_posix() for p in TARGET.rglob('*') if p.is_file()}
        assert existing == set(sources), 'existing target has missing/unknown files: refuse overwrite'
        assert all(sha(TARGET / name) == info['sha256'] for name, info in before.items()), 'existing target contents differ: refuse overwrite'
    else:
        TARGET.mkdir(parents=True, exist_ok=False)
        for name, source in sources.items():
            destination = TARGET / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    after = {name: {'bytes': (TARGET / name).stat().st_size, 'sha256': sha(TARGET / name)} for name in sources}
    assert before == after, 'copy fingerprint mismatch'
    assert all(sha(source) == before[name]['sha256'] for name, source in sources.items()), 'source changed during copy'
    env = os.environ.copy()
    env['npm_config_cache'] = str(ROOT / '.npm-cache')
    env['npm_config_prefix'] = str(TARGET)
    env['TEMP'] = env['TMP'] = str(OUT / 'temp')
    node_version = subprocess.check_output([str(TARGET / 'node.exe'), '--version'], env=env, text=True).strip()
    npm_version = subprocess.check_output([str(TARGET / 'node.exe'), str(TARGET / 'node_modules/npm/bin/npm-cli.js'), '--version'], env=env, text=True).strip()
    assert node_version == 'v24.19.0' and npm_version == '10.8.2'
    record = dict(mode=mode, target=str(TARGET), node_version=node_version, npm_version=npm_version,
                  node_sha256_before=before['node.exe']['sha256'], node_sha256_after=after['node.exe']['sha256'],
                  all_files_equal=True, files=len(before), source_and_target=before,
                  user_system_PATH_modified=False)
    destination = OUT / ('toolchain-copy-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
    destination.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='')
    print(json.dumps({k: v for k, v in record.items() if k != 'source_and_target'}, indent=2))
    print('receipt=' + str(destination))


if __name__ == '__main__':
    main()
