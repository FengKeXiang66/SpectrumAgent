param([Parameter(Mandatory=$true)][string]$Label)
$ErrorActionPreference='Stop'
$root='E:\AI_Agent'
$out=Join-Path $root 'artifacts\step3\checkpoint-4\release-custom-protocol-20261018\final-canonical-20261019'
if($Label -notmatch '^[a-z0-9-]+$'){throw 'Label must be an ASCII filename component'}
$record=Join-Path $out ($Label+'-launch.json')
if(Test-Path -LiteralPath $record){throw 'Do not overwrite prior launch evidence'}
$binding=Get-Content -LiteralPath (Join-Path $out 'candidate-repro.json') -Raw|ConvertFrom-Json
$exe=Join-Path $root 'src-tauri\target\repro-check\release\spectrum-agent.exe'
if((Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant() -cne $binding.shell_sha256){throw 'Candidate exe changed'}
$env:TEMP=Join-Path $out 'temp'
$env:TMP=$env:TEMP
$env:WEBVIEW2_USER_DATA_FOLDER=Join-Path $env:TEMP ('webview-'+$Label+'-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
$env:SPECTRUM_ACCEPTANCE_PROBE='1'
$env:SPECTRUM_ENGINE_EXE='E:\AI_Agent\invalid-production-override\app.exe'
New-Item -ItemType Directory -Path $env:TEMP -Force|Out-Null
$listeners=@(Get-NetTCPConnection -LocalPort 1420 -State Listen -ErrorAction SilentlyContinue)
if($listeners.Count){throw 'Vite devUrl still listens on port1420; embedded-resource test invalid'}
$before=[DateTime]::UtcNow.ToString('o')
$process=Start-Process -FilePath $exe -WorkingDirectory $env:TEMP -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out ($Label+'.stdout.txt')) -RedirectStandardError (Join-Path $out ($Label+'.stderr.txt'))
[ordered]@{launch_before_utc=$before;pid=$process.Id;process_created_utc=$process.StartTime.ToUniversalTime().ToString('o');shell_sha256=$binding.shell_sha256;features='custom-protocol';working_directory=$env:TEMP;invalid_engine_override=$env:SPECTRUM_ENGINE_EXE;vite_port1420_listeners=0;webview_profile=$env:WEBVIEW2_USER_DATA_FOLDER;cold_definition='new WebView profile; OS file cache not purged';acceptance_probe=$true;acceptance_close_observation_ms=350}|ConvertTo-Json|Set-Content -LiteralPath $record -Encoding utf8
Get-Content -LiteralPath $record -Raw
