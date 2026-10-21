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
    & $Executable @Arguments *> $log
    $stepExit = $LASTEXITCODE
    Get-Content -LiteralPath $log -Tail 12
    if ($stepExit -ne 0) { throw "$Name failed (exit $stepExit). Full log: $log" }
}

$inputs = [ordered]@{version=$config.version;source_commit=(git rev-parse HEAD);build_root=$buildRoot;node=(& $node --version);python=(& $python --version);cargo=(cargo --version);features='custom-protocol';freeze_spec='scripts/backend.spec';signed=$false}
$inputs | ConvertTo-Json | Set-Content -LiteralPath "$buildRoot\build-inputs.json" -Encoding utf8
Run-Step 'freeze' $python @('-m','PyInstaller','--noconfirm',"$root\scripts\backend.spec")
$frozen = "$buildRoot\engine-dist\app"
Run-Step 'frozen-smoke' $python @("$root\scripts\verify_frozen_backend.py",'smoke','--exe',"$frozen\app.exe",'--output',"$buildRoot\frozen-smoke")
Run-Step 'stage' $python @("$root\scripts\verify_frozen_backend.py",'stage','--source',$frozen,'--build-root',$buildRoot)

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
Run-Step 'bundled-smoke' $python @("$root\scripts\verify_frozen_backend.py",'smoke','--exe',"$env:CARGO_TARGET_DIR\release\resources\backend\app.exe",'--output',"$buildRoot\bundled-smoke")
$nsi = "$env:CARGO_TARGET_DIR\release\nsis\x64\installer.nsi"
if (-not (Select-String -LiteralPath $nsi -SimpleMatch 'plastic.json')) { throw 'NSIS payload script omits plastic.json' }
Copy-Item -LiteralPath $installer -Destination (Join-Path $buildRoot $installerName)
$delivery = Get-Item -LiteralPath (Join-Path $buildRoot $installerName)
$result = [ordered]@{version=$config.version;installer=$delivery.FullName;bytes=$delivery.Length;sha256=(Get-FileHash -LiteralPath $delivery.FullName -Algorithm SHA256).Hash;frozen_smoke='passed';bundled_smoke='passed';nsis_includes_catalog=$true;manual_installed_ui='not performed';signed=$false;build_root=$buildRoot}
$result | ConvertTo-Json | Set-Content -LiteralPath "$buildRoot\release-result.json" -Encoding utf8
Write-Host "SUCCESS: $($delivery.FullName)"
$result | ConvertTo-Json
