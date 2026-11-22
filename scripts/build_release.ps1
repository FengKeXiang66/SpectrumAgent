param()
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$config = Get-Content -LiteralPath "$root\src-tauri\tauri.conf.json" -Raw | ConvertFrom-Json
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$buildRoot = Join-Path $root "artifacts\releases\$($config.version)-$stamp"
New-Item -ItemType Directory -Path $buildRoot | Out-Null
$python = "$root\.venv\Scripts\python.exe"
$nodeDirectory = "$root\.toolchains\node24.19.0-npm10.8.2"
$node = "$nodeDirectory\node.exe"
$npm = "$nodeDirectory\node_modules\npm\bin\npm-cli.js"
foreach ($required in @($python, $node, $npm, "$root\src-tauri\target\.tauri\NSIS\Bin\makensis.exe")) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing existing packaging prerequisite (no install/download attempted): $required" }
}
$env:SPECTRUM_BUILD_ROOT = $buildRoot
$env:PATH = "$nodeDirectory;$env:PATH"
$env:CARGO_HOME = "$root\.cargo-home"
$env:CARGO_TARGET_DIR = "$root\src-tauri\target"
$env:CARGO_NET_OFFLINE = 'true'
$env:npm_config_cache = "$root\.npm-cache"
$env:PYTHONIOENCODING = 'utf-8'
$env:TEMP = Join-Path $buildRoot 'temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP | Out-Null
Remove-Item Env:RUSTFLAGS -ErrorAction SilentlyContinue

function Run-Step([string]$Name, [string]$Executable, [string[]]$Arguments) {
    $log = Join-Path $buildRoot "$Name.txt"
    Write-Host "[$Name] $Executable $($Arguments -join ' ')"
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Executable @Arguments > $log 2>&1
    $ErrorActionPreference = $prevEAP
    $stepExit = $LASTEXITCODE
    Get-Content -LiteralPath $log -Tail 12
    if ($stepExit -ne 0) { throw "$Name failed (exit $stepExit). Full log: $log" }
}

$inputs = [ordered]@{version=$config.version;source_commit=(git rev-parse HEAD);build_root=$buildRoot;node=(& $node --version);python=(& $python --version);cargo=(cargo --version);features='custom-protocol';freeze_spec='scripts/backend.spec';slim_backend=($env:SPECTRUMAGENT_SLIM_BACKEND -eq '1');signed=$false}
$inputs | ConvertTo-Json | Set-Content -LiteralPath "$buildRoot\build-inputs.json" -Encoding utf8
Run-Step 'freeze' $python @('-m','PyInstaller','--noconfirm',"$root\scripts\backend.spec")
$frozen = "$buildRoot\engine-dist\app"
# Packaging needs resource staging even when the historical verification suite
# is absent. Keep that production operation here, independent of test fixtures.
$resourceScript = @'
import hashlib
import json
from pathlib import Path
import shutil
import sys

operation, workspace, payload, output = sys.argv[1:]
root = Path(workspace).resolve()
source = Path(payload)
build_root = Path(output)

def checked(path):
    path = Path(path).absolute()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f"Packaging path must stay within workspace: {path}")
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink() or item.is_junction():
            raise ValueError(f"Linked packaging path: {item}")
    if not path.resolve().is_relative_to(root):
        raise ValueError(f"Resolved packaging path escapes workspace: {path}")
    return path

source, build_root = checked(source), checked(build_root)

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def inventory(directory):
    entries = []
    for path in sorted(directory.rglob('*')):
        checked(path)
        if path.is_file():
            entries.append({'path': path.relative_to(directory).as_posix(),
                            'bytes': path.stat().st_size, 'sha256': sha(path)})
    if not entries:
        raise ValueError(f"Empty backend payload: {directory}")
    return entries

originals = list((root / 'src-python' / 'spectrumagent').rglob('*.json'))
if not originals or not (source / 'app.exe').is_file():
    raise ValueError('Backend executable or source package JSON resources missing')
for original in originals:
    relative = original.relative_to(root / 'src-python' / 'spectrumagent')
    frozen_data = checked(source / '_internal' / 'spectrumagent' / relative)
    if not frozen_data.is_file() or sha(original) != sha(frozen_data):
        raise ValueError(f"Frozen JSON missing or different: {relative}")
expected = inventory(source)
if operation == 'stage':
    destination = checked(root / 'src-tauri' / 'resources' / 'backend')
    backup = checked(build_root / 'prior-resources-backend')
    if backup.exists():
        raise ValueError('Refuse to overwrite a previous backend backup')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        inventory(destination)
        destination.rename(backup)
    shutil.copytree(source, destination)
    if inventory(destination) != expected:
        raise ValueError('Staged backend byte inventory differs')
elif operation == 'bundled':
    staged = checked(root / 'src-tauri' / 'resources' / 'backend')
    actual = {entry['path']: entry for entry in expected}
    for entry in inventory(staged):
        if actual.get(entry['path']) != entry:
            raise ValueError(f"Bundled backend file missing or different: {entry['path']}")
else:
    raise ValueError(f"Unknown resource operation: {operation}")
(build_root / f'{operation}-inventory.json').write_text(
    json.dumps({'source': str(source), 'files': expected}, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(f'{operation}: verified {len(expected)} files and {len(originals)} JSON resources')
'@
Run-Step 'stage' $python @('-B','-c',$resourceScript,'stage',$root,$frozen,$buildRoot)

# Preserve the previous installer before the bundler regenerates that filename.
$installerName = "$($config.productName)_$($config.version)_x64-setup.exe"
$installer = Join-Path $env:CARGO_TARGET_DIR "release\bundle\nsis\$installerName"
if (Test-Path -LiteralPath $installer) {
    $absolute = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $installer).Path)
    $backup = [IO.Path]::GetFullPath((Join-Path $buildRoot 'prior-installer.exe'))
    if (-not $absolute.StartsWith("$root\",[StringComparison]::OrdinalIgnoreCase) -or -not $backup.StartsWith("$root\",[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Installer backup paths must stay within this workspace'
    }
    Move-Item -LiteralPath $absolute -Destination $backup
}
Run-Step 'tauri-build' $node @($npm,'run','tauri','--','build','--features','custom-protocol','--bundles','nsis','--ci','--no-binary-patching','--','--locked','--offline')
if (-not (Test-Path -LiteralPath $installer)) { throw "Installer missing: $installer" }
Run-Step 'bundled-assets' $python @('-B','-c',$resourceScript,'bundled',$root,"$env:CARGO_TARGET_DIR\release\resources\backend",$buildRoot)
$nsi = "$env:CARGO_TARGET_DIR\release\nsis\x64\installer.nsi"
if (-not (Select-String -LiteralPath $nsi -SimpleMatch 'plastic.json')) { throw 'NSIS payload script omits plastic.json' }
Copy-Item -LiteralPath $installer -Destination (Join-Path $buildRoot $installerName)
$delivery = Get-Item -LiteralPath (Join-Path $buildRoot $installerName)
$result = [ordered]@{version=$config.version;installer=$delivery.FullName;bytes=$delivery.Length;sha256=(Get-FileHash -LiteralPath $delivery.FullName -Algorithm SHA256).Hash;resource_inventory='passed';frozen_smoke='not performed (verification suite removed)';bundled_smoke='not performed (verification suite removed)';nsis_includes_catalog=$true;manual_installed_ui='not performed';signed=$false;build_root=$buildRoot}
$result | ConvertTo-Json | Set-Content -LiteralPath "$buildRoot\release-result.json" -Encoding utf8
Write-Host "SUCCESS: $($delivery.FullName)"
$result | ConvertTo-Json
