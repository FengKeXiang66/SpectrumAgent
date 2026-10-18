"""Read-only HTTPS metadata; never downloads a package archive or runs a package manager."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from urllib.parse import quote

OUT = Path(__file__).resolve().parent
PACKAGES = ['react', 'react-dom', '@tauri-apps/api', 'vite', 'typescript',
            '@vitejs/plugin-react', '@types/react', '@types/react-dom', '@types/node', '@tauri-apps/cli']
CRATES = ['tauri', 'tauri-build', 'tauri-plugin-single-instance', 'tauri-plugin-opener']


def get(url):
    result = subprocess.run([
        r'C:\Windows\System32\curl.exe', '--ssl-revoke-best-effort',
        '--silent', '--show-error', '--fail', '--max-time', '25',
        '--user-agent', 'SpectrumAgent-toolchain-readonly-probe/0.1', url,
    ], shell=False, capture_output=True)
    if result.returncode:
        raise RuntimeError(f'metadata GET failed: {url}; curl={result.returncode}; {result.stderr.decode(errors="replace")}')
    return json.loads(result.stdout)


def probe_npm(name):
    pin = {'typescript': '5.9.3', '@types/node': '24.10.1'}.get(name, 'latest')
    url = 'https://registry.npmjs.org/' + quote(name, safe='') + '/' + pin
    data = get(url)
    return {'ecosystem': 'npm', 'name': name, 'url': url, 'raw': data,
            'version': data['version'], 'engines': data.get('engines'),
            'peerDependencies': data.get('peerDependencies'),
            'peerDependenciesMeta': data.get('peerDependenciesMeta'),
            'dependencies': data.get('dependencies'),
            'optionalDependencies': data.get('optionalDependencies'),
            'dist': data.get('dist')}


def probe_crate(name):
    url = 'https://crates.io/api/v1/crates/' + name
    listing = get(url)
    version = listing['crate']['max_stable_version']
    data = get(url + '/' + version)
    return {'ecosystem': 'cargo', 'name': name, 'url': url + '/' + version, 'raw': data,
            'version': version, 'rust_version': data['version'].get('rust_version'),
            'features': data['version'].get('features'), 'checksum': data['version'].get('checksum')}


if __name__ == '__main__':
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = [executor.submit(probe_npm, name) for name in PACKAGES]
        jobs += [executor.submit(probe_crate, name) for name in CRATES]
        for job in jobs:
            item = job.result()
            results.append(item)
            print(json.dumps({k: v for k, v in item.items() if k not in ('raw', 'features', 'dist', 'checksum')}, ensure_ascii=False), flush=True)
    payload = {'fetched_at': datetime.now(timezone.utc).isoformat(), 'method': 'HTTPS GET metadata only', 'results': results}
    target = OUT / ('registry-metadata-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='')
    print('metadata_file=' + str(target))
