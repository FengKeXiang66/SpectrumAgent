param([switch]$Offline)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$config = Get-Content -LiteralPath "$root\src-tauri\tauri.conf.json" -Raw | ConvertFrom-Json
$toolchains = Join-Path $root '.toolchains'
$python = $env:SPECTRUMAGENT_DEV_PYTHON
if (-not $python) {
    $python = @("$toolchains\dev-venv\Scripts\python.exe", "$root\.venv\Scripts\python.exe") |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
if (-not $python -or -not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Set SPECTRUMAGENT_DEV_PYTHON to a CPython 3.12.13 interpreter with PyInstaller installed.'
}
$python = (Resolve-Path -LiteralPath $python).Path
& $python -c 'import sys; import struct; sys.exit(sys.version) if sys.implementation.name != ''cpython'' or sys.version_info[:3] != (3, 12, 13) or struct.calcsize(''P'') != 8 else None; import PyInstaller'
if ($LASTEXITCODE -ne 0) { throw "CPython 3.12.13 with PyInstaller required: $python" }

$node = @("$toolchains\node24.19.0-npm10.8.2\node.exe", "$toolchains\node-v24.19.0-win-x64\node.exe") |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $node) { $node = (Get-Command node.exe -CommandType Application).Source }
$nodeDirectory = Split-Path -Parent $node
$npmCommand = Get-Command npm.cmd -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$npmCandidates = @(
    "$toolchains\npm-10.8.2\node_modules\npm\bin\npm-cli.js",
    "$nodeDirectory\node_modules\npm\bin\npm-cli.js"
)
if ($nodeDirectory -eq "$toolchains\node24.19.0-npm10.8.2") {
    [array]::Reverse($npmCandidates)
}
if ($npmCommand) {
    $npmCandidates += "$(Split-Path -Parent $npmCommand.Source)\node_modules\npm\bin\npm-cli.js"
}
$npm = $npmCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $npm) { throw "npm-cli.js not found for $node" }
$npmVersion = & $node $npm --version
if ($LASTEXITCODE -ne 0) { throw "npm-cli.js failed: $npm" }
$env:PATH = "$nodeDirectory;$env:PATH"

$env:CARGO_HOME = "$root\.cargo-home"
$env:CARGO_TARGET_DIR = "$root\src-tauri\target"
if (Test-Path -LiteralPath "$toolchains\rustup" -PathType Container) {
    $env:RUSTUP_HOME = "$toolchains\rustup"
    $env:PATH = "$env:CARGO_HOME\bin;$env:PATH"
}
$vcvars = "$toolchains\VSBuildTools\VC\Auxiliary\Build\vcvars64.bat"
if ((-not (Get-Command cl.exe -ErrorAction SilentlyContinue) -or
     -not (Get-Command link.exe -ErrorAction SilentlyContinue)) -and (Test-Path -LiteralPath $vcvars -PathType Leaf)) {
    $vcEnvironment = & $env:ComSpec /d /c ('call "{0}" >nul && set' -f $vcvars)
    if ($LASTEXITCODE -ne 0) { throw "Failed to initialize x64 MSVC: $vcvars" }
    foreach ($entry in $vcEnvironment) {
        if ($entry -match '^([^=]+)=(.+)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2]) }
    }
}
foreach ($tool in @('cargo.exe', 'cl.exe', 'link.exe')) {
    if (-not (Get-Command $tool -CommandType Application -ErrorAction SilentlyContinue)) {
        throw "Packaging tool not found: $tool"
    }
}
$tauriTools = "$env:CARGO_TARGET_DIR\.tauri"
$nsis = Join-Path $tauriTools 'NSIS'
$nsisFiles = @(
    'makensis.exe', 'Bin/makensis.exe', 'NSIS.exe', 'Stubs/lzma-x86-unicode', 'Stubs/lzma_solid-x86-unicode',
    'Plugins/x86-unicode/additional/nsis_tauri_utils.dll', 'Include/MUI2.nsh', 'Include/FileFunc.nsh',
    'Include/x64.nsh', 'Include/nsDialogs.nsh', 'Include/WinMessages.nsh', 'Include/Win/COM.nsh',
    'Include/Win/Propkey.nsh', 'Include/Win/RestartManager.nsh'
)
$missing = $nsisFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $nsis $_) -PathType Leaf) }
$webview = Get-ChildItem -LiteralPath "$tauriTools\x64" -Filter '*webview2*.exe' -File -Recurse -ErrorAction SilentlyContinue |
    Where-Object Length -GT 10MB | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
$cached = -not $missing -and $webview -and
    ((Get-FileHash -LiteralPath "$nsis\NSIS.exe" -Algorithm SHA1).Hash -eq '6D45D4E8CCF18FE1FDAC9164058F356102A2ECF2') -and
    ((Get-FileHash -LiteralPath "$nsis\Plugins\x86-unicode\additional\nsis_tauri_utils.dll" -Algorithm SHA1).Hash -eq '75197FEE3C6A814FE035788D1C34EAD39349B860')
if ($Offline -and -not $cached) { throw "Offline packaging requires cached NSIS and x64 WebView2 in $tauriTools" }
$cargoArgs = @('--locked')
if ($cached) {
    $env:CARGO_NET_OFFLINE = 'true'
    $cargoArgs += '--offline'
} else {
    Remove-Item Env:CARGO_NET_OFFLINE -ErrorAction SilentlyContinue
}
$env:npm_config_cache = "$root\.npm-cache"
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$buildRoot = Join-Path $root "artifacts\releases\$($config.version)-$stamp"
New-Item -ItemType Directory -Path $buildRoot | Out-Null
$env:SPECTRUM_BUILD_ROOT = $buildRoot
# Tauri invokes npm again for beforeBuildCommand. Use the same npm as the
# outer command even when npm-cli.js comes from a standalone npm package.
$shimDirectory = Join-Path $buildRoot 'bin'
New-Item -ItemType Directory -Path $shimDirectory | Out-Null
$env:SPECTRUM_RELEASE_NODE = $node
$env:SPECTRUM_RELEASE_NPM = $npm
Set-Content -LiteralPath "$shimDirectory\npm.cmd" -Encoding ascii -Value @(
    '@echo off', '"%SPECTRUM_RELEASE_NODE%" "%SPECTRUM_RELEASE_NPM%" %*'
)
$env:PATH = "$shimDirectory;$env:PATH"
$env:TEMP = Join-Path $buildRoot 'temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Path $env:TEMP | Out-Null
Remove-Item Env:RUSTFLAGS -ErrorAction SilentlyContinue

function Write-Utf8([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

$tauriConfigArgs = @()
if ($cached) {
    # Tauri 2.12.3 resolves the WebView2 download URL over HTTP even on a cache
    # hit. Suppress that lookup and embed the cached x64 runtime in the same
    # installer branch via a build-local copy of the project's NSIS template.
    $templatePath = Join-Path $buildRoot 'installer-offline.nsi'
    $template = Get-Content -LiteralPath "$root\src-tauri\nsis\installer.nsi" -Raw
    $webviewPath = $webview.FullName.Replace('$', '$$').Replace('`', '$\`')
    $template = $template.Replace('{{install_webview2_mode}}', 'offlineInstaller').Replace('{{webview2_installer_path}}', $webviewPath)
    if ($config.bundle.windows.webviewInstallMode.silent -eq $false) {
        $template = $template.Replace('{{webview2_installer_args}}', '')
    }
    Write-Utf8 $templatePath $template
    $overrides = @{bundle=@{windows=@{webviewInstallMode=@{type='skip'};nsis=@{template=$templatePath}}}}
    $overridePath = Join-Path $buildRoot 'tauri-offline.json'
    Write-Utf8 $overridePath ($overrides | ConvertTo-Json -Depth 8)
    $tauriConfigArgs = @('--config', $overridePath)
}

function Run-Step([string]$Name, [string]$Executable, [string[]]$Arguments) {
    $log = Join-Path $buildRoot "$Name.txt"
    Write-Host "[$Name] $Executable $($Arguments -join ' ')"
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Executable @Arguments > $log 2>&1
        $stepExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEAP
    }
    Get-Content -LiteralPath $log -Tail 12
    if ($stepExit -ne 0) { throw "$Name failed (exit $stepExit). Full log: $log" }
}

$sourceCommit = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Unable to record the Git source revision.' }
$inputs = [ordered]@{version=$config.version;source_commit=$sourceCommit;build_root=$buildRoot;node=(& $node --version);npm=$npmVersion;python=(& $python --version);cargo=(cargo --version);cargo_offline=($cargoArgs -contains '--offline');features='custom-protocol';freeze_spec='scripts/backend.spec';slim_backend=($env:SPECTRUMAGENT_SLIM_BACKEND -eq '1');signed=$false}
Write-Utf8 "$buildRoot\build-inputs.json" ($inputs | ConvertTo-Json)
Run-Step 'freeze' $python @('-m','PyInstaller','--noconfirm',"$root\scripts\backend.spec")
$frozen = "$buildRoot\engine-dist\app"
# Packaging needs resource staging even when the historical verification suite
# is absent. Keep that production operation here, independent of test fixtures.
$resourceScript = @'
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
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
destination = checked(root / 'src-tauri' / 'resources' / 'backend')
backup = checked(build_root / 'prior-resources-backend')
prepared = checked(build_root / 'staged-backend')
if operation == 'restore':
    destination.rename(prepared)
    if backup.exists():
        backup.rename(destination)
    print('Restored the original source resource tree')
    sys.exit(0)

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
    if backup.exists():
        raise ValueError('Refuse to overwrite a previous backend backup')
    shutil.copytree(source, prepared)
    if inventory(prepared) != expected:
        raise ValueError('Staged backend byte inventory differs')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        inventory(destination)
        destination.rename(backup)
    try:
        prepared.rename(destination)
    except OSError:
        if backup.exists():
            backup.rename(destination)
        raise
elif operation == 'bundled':
    if inventory(destination) != expected:
        raise ValueError('Bundled backend byte inventory differs from stage')
    nsi = source.parent.parent / 'nsis' / 'x64' / 'installer.nsi'
    script = checked(nsi).read_text('utf-8-sig')
    targets = {}
    for name, path in re.findall(r'^\s*File /a "/oname=([^"]+)" "([^"]+)"', script, re.MULTILINE):
        file = PureWindowsPath(name)
        if file.is_relative_to(PureWindowsPath('resources/backend')):
            relative = file.relative_to(PureWindowsPath('resources/backend')).as_posix()
            if relative in targets:
                raise ValueError(f'Duplicate NSIS backend file: {relative}')
            targets[relative] = checked(Path(path))
    if set(targets) != {entry['path'] for entry in expected}:
        raise ValueError('NSIS resource directives do not match the complete backend inventory')
    for entry in expected:
        if sha(targets[entry['path']]) != entry['sha256']:
            raise ValueError(f"NSIS source file differs: {entry['path']}")
    webview = re.search(r'^!define WEBVIEW2INSTALLERPATH "([^"]+)"', script, re.MULTILINE)
    if ('!define ARCH "x64"' not in script or '!define INSTALLWEBVIEW2MODE "offlineInstaller"' not in script or not webview
            or not checked(webview[1].replace('$$', '$').replace('$\\`', '`')).is_file()
            or 'File "/oname=$TEMP\\MicrosoftEdgeWebView2RuntimeInstaller.exe" "${WEBVIEW2INSTALLERPATH}"' not in script):
        raise ValueError('NSIS installer does not embed the offline WebView2 runtime')
    shutil.copyfile(nsi, build_root / 'installer.nsi')
else:
    raise ValueError(f"Unknown resource operation: {operation}")
(build_root / f'{operation}-inventory.json').write_text(
    json.dumps({'source': str(source), 'files': expected}, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(f'{operation}: verified {len(expected)} files and {len(originals)} JSON resources')
'@
$resourceHelper = Join-Path $buildRoot 'verify_resources.py'
Write-Utf8 $resourceHelper $resourceScript
Run-Step 'stage' $python @('-B',$resourceHelper,'stage',$root,$frozen,$buildRoot)

try {
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
Run-Step 'tauri-build' $node (@($npm,'run','tauri','--','build','--features','custom-protocol','--bundles','nsis','--ci','--no-binary-patching') + $tauriConfigArgs + @('--') + $cargoArgs)
if (-not (Test-Path -LiteralPath $installer)) { throw "Installer missing: $installer" }
$bundled = "$env:CARGO_TARGET_DIR\release\resources\backend"
Run-Step 'bundled-assets' $python @('-B',$resourceHelper,'bundled',$root,$bundled,$buildRoot)
$smoke = Join-Path $buildRoot 'frozen-smoke'
New-Item -ItemType Directory -Path $smoke | Out-Null
Run-Step 'frozen-smoke' $python @('-B',"$PSScriptRoot\verify_frozen_backend.py","$frozen\app.exe","$smoke\frozen")
Run-Step 'bundled-smoke' $python @('-B',"$PSScriptRoot\verify_frozen_backend.py","$bundled\app.exe","$smoke\bundled")
Copy-Item -LiteralPath $installer -Destination (Join-Path $buildRoot $installerName)
$delivery = Get-Item -LiteralPath (Join-Path $buildRoot $installerName)
$result = [ordered]@{version=$config.version;installer=$delivery.FullName;bytes=$delivery.Length;sha256=(Get-FileHash -LiteralPath $delivery.FullName -Algorithm SHA256).Hash;resource_inventory='passed';nsis_includes_catalog=$true;nsis_offline_webview2=$true;manual_installed_ui='not performed';signed=$false;build_root=$buildRoot}
foreach ($kind in @('frozen','bundled')) {
    $result["${kind}_smoke"] = Get-Content -LiteralPath "$smoke\$kind\checks.json" -Raw | ConvertFrom-Json
}
Write-Utf8 "$buildRoot\release-result.json" ($result | ConvertTo-Json -Depth 5)
Write-Host "SUCCESS: $($delivery.FullName)"
$result | ConvertTo-Json -Depth 5
} finally {
    # The source resource tree can include files tracked by older commits.
    # Keep the new staged payload with the build and restore the original tree.
    Run-Step 'restore-resources' $python @('-B',$resourceHelper,'restore',$root,$frozen,$buildRoot)
}
