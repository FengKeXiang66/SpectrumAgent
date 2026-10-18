param([ValidateRange(5,100)][int]$Rounds=5)
$ErrorActionPreference='Stop'
$session=Join-Path $PSScriptRoot ('session-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $session | Out-Null
$env:PYTHONUTF8='1'
$python='E:\AI_Agent\.venv\Scripts\python.exe'
Write-Output ('> '+$python+' '+(Join-Path $PSScriptRoot 'lifecycle_regression.py')+' --output '+(Join-Path $session 'runtime')+' --rounds '+$Rounds)
& $python (Join-Path $PSScriptRoot 'lifecycle_regression.py') --output (Join-Path $session 'runtime') --rounds $Rounds 2>&1 | Tee-Object -LiteralPath (Join-Path $session 'selfcheck-output.txt')
$code=$LASTEXITCODE
Write-Output ('session='+$session+' exit_code='+$code)
if($code -ne 0){Write-Output 'FAIL: runtime/summary.json identifies the failed case; failure cleanup is TEST_HYGIENE_ONLY.'}
exit $code
