param([ValidateRange(5, 100)][int]$Rounds = 5)

$ErrorActionPreference = 'Stop'
$stepRoot = $PSScriptRoot
$python = 'E:\AI_Agent\.venv\Scripts\python.exe'
$runId = 'session-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')
$revision = Join-Path $stepRoot 'revision-01'
$session = Join-Path $revision $runId
New-Item -ItemType Directory -Path $session | Out-Null
$env:PYTHONUTF8 = '1'
$exitCode = 1
Start-Transcript -LiteralPath (Join-Path $session 'selfcheck-output.txt') | Out-Null
try {
    Write-Output '> Full dev + frozen regression: CTRL_BREAK immediate cleanup; CTRL_C and taskkill recovery are separate cases.'
    Write-Output '> The controller uses the specified venv; frozen engines are launched directly as app.exe without an interpreter or command shell.'
    Write-Output ('> & ' + $python + ' ' + (Join-Path $stepRoot 'lifecycle_regression.py') + ' --output ' + (Join-Path $session 'runtime') + ' --rounds ' + $Rounds)
    & $python (Join-Path $stepRoot 'lifecycle_regression.py') --output (Join-Path $session 'runtime') --rounds $Rounds
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) { Write-Output 'FAIL: see runtime/summary.json for the failed case and redacted residual handshake.' }
    else { Write-Output 'PASS: complete matrix, ownership protection, mutex failure/abandonment, diagnostics, curl, bundle inventory and DLL failure checks.' }
} finally {
    $session | Set-Content -LiteralPath (Join-Path $revision 'latest-session.txt') -Encoding utf8NoBOM
    Stop-Transcript | Out-Null
}
exit $exitCode
