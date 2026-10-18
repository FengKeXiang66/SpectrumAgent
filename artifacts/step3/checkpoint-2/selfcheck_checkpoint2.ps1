param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$root = 'E:\AI_Agent'
$env:CARGO_HOME = Join-Path $root '.cargo-home'
$env:CARGO_TARGET_DIR = Join-Path $root 'src-tauri\target'
$env:TEMP = Join-Path $PSScriptRoot 'temp'
$env:TMP = $env:TEMP
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
Write-Output "CARGO_HOME=$env:CARGO_HOME"
Write-Output "CARGO_TARGET_DIR=$env:CARGO_TARGET_DIR"
Write-Output "TEMP=$env:TEMP"
if (-not $SkipBuild) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    foreach ($profile in @('debug', 'release')) {
        $arguments = @('build', '--manifest-path', "$root\src-tauri\Cargo.toml", '--locked', '--offline', '--features', 'test-probes', '--bin', 'supervisor-probe')
        if ($profile -eq 'release') { $arguments += '--release' }
        Write-Output "cargo $($arguments -join ' ')"
        & 'C:\Users\Administrator\.cargo\bin\cargo.exe' @arguments 2>&1 | Tee-Object -FilePath (Join-Path $PSScriptRoot "build-$profile-$stamp.txt")
        if ($LASTEXITCODE -ne 0) { throw "构建失败：$profile，见对应原始输出" }
    }
}
& "$root\.venv\Scripts\python.exe" (Join-Path $PSScriptRoot 'selfcheck_checkpoint2.py')
exit $LASTEXITCODE
