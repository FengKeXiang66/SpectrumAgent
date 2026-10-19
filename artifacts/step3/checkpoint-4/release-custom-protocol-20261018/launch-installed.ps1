$ErrorActionPreference='Stop'
$out=$PSScriptRoot
$state=Get-Content -LiteralPath (Join-Path $out 'host-install-state.json') -Raw|ConvertFrom-Json
$exe=Join-Path $state.program 'spectrum-agent.exe'
if((Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant() -cne $state.shell_sha256){throw 'Installed exe changed'}
$env:TEMP=Join-Path $out 'temp';$env:TMP=$env:TEMP
$env:WEBVIEW2_USER_DATA_FOLDER=Join-Path $out 'temp\webview-installed'
$env:SPECTRUM_ACCEPTANCE_PROBE='1'
$env:SPECTRUM_ENGINE_EXE='E:\AI_Agent\invalid-installed-override\app.exe'
if(@(Get-NetTCPConnection -LocalPort 1420 -State Listen -ErrorAction SilentlyContinue).Count){throw 'Dev server is listening'}
$before=[DateTime]::UtcNow.ToString('o')
$p=Start-Process -FilePath $exe -WorkingDirectory $env:TEMP -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out 'installed.stdout.txt') -RedirectStandardError (Join-Path $out 'installed.stderr.txt')
[ordered]@{pid=$p.Id;launch_before_utc=$before;exe=$exe;features='custom-protocol';sha256=$state.shell_sha256;working_directory=$env:TEMP;invalid_engine_override=$env:SPECTRUM_ENGINE_EXE;vite_port1420_listeners=0;scope='host installation smoke; clean VM still pending'}|ConvertTo-Json|Tee-Object -FilePath (Join-Path $out 'installed-launch.json')
