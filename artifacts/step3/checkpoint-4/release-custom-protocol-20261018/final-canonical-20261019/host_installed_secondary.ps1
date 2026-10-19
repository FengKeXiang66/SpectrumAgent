$ErrorActionPreference='Stop'
$result=[ordered]@{status='running';checked_utc=[DateTime]::UtcNow.ToString('o');error=$null}
try{
 $launch=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'installed-probe-launch.json') -Raw|ConvertFrom-Json
 $program=Split-Path -Parent $launch.exe
 $hs=Join-Path $env:LOCALAPPDATA 'SpectrumAgent\run\handshake.json'
 $before=[IO.File]::ReadAllBytes($hs)
 $second=Start-Process -FilePath $launch.exe -WindowStyle Hidden -PassThru
 if(-not $second.WaitForExit(10000)){throw 'Secondary instance did not exit'}
 $after=[IO.File]::ReadAllBytes($hs)
 $shells=@(Get-CimInstance Win32_Process -Filter "Name='spectrum-agent.exe'"|Where-Object {$_.ExecutablePath -and $_.ExecutablePath.Replace('\\?\','') -ieq $launch.exe})
 $children=@(Get-CimInstance Win32_Process -Filter ("ParentProcessId="+$launch.pid+" AND Name='app.exe'"))
 $result.primary_pid=$launch.pid;$result.secondary_pid=$second.Id;$result.secondary_exit=$second.ExitCode;$result.handshake_bytes_unchanged=([Convert]::ToBase64String($before) -ceq [Convert]::ToBase64String($after));$result.remaining_shells=@($shells|Select-Object ProcessId,ExecutablePath);$result.engine_processes=@($children|Select-Object ProcessId,ExecutablePath)
 if($second.ExitCode -ne 0 -or $shells.Count -ne 1 -or $shells[0].ProcessId -ne $launch.pid -or $children.Count -ne 1 -or -not $result.handshake_bytes_unchanged){throw 'Installed single-instance check failed'}
 $result.status='passed'
}catch{$result.status='failed';$result.error=$_.Exception.Message}
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'installed-single-instance-result.json'),($result|ConvertTo-Json -Depth 10)+"`n",[Text.UTF8Encoding]::new($false))
