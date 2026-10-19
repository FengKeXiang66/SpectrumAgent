param([ValidatePattern('^installed-(probe[0-9]*|delivery)$')][string]$Label='installed-probe',
 [ValidateSet('candidate.json','candidate-repro.json')][string]$BindingName='candidate-repro.json')
$ErrorActionPreference='Stop'
$out=$PSScriptRoot
. (Join-Path $out 'real_root.ps1')
$receipt=Join-Path $out ($Label+'-result.json')
$processHandle=[IntPtr]::Zero
$result=[ordered]@{status='running';context='Explorer broker host process';error=$null}
function Save-Json([string]$Name,$Value){
 $Name=$Name.Replace('installed-probe',$Label)
 $path=Join-Path $out $Name
 if(Test-Path -LiteralPath $path){throw "Evidence exists: $path"}
 [IO.File]::WriteAllText($path,($Value|ConvertTo-Json -Depth 18)+"`n",[Text.UTF8Encoding]::new($false))
}
function Hash-Bytes([byte[]]$Value){
 $algorithm=[Security.Cryptography.SHA256]::Create()
 try{([BitConverter]::ToString($algorithm.ComputeHash($Value))).Replace('-','').ToLowerInvariant()}finally{$algorithm.Dispose()}
}
function Copy-Segment([string]$Source,[long]$Offset,[string]$Name,[string]$Secret,[string]$WholeHandshake){
 $Name=$Name.Replace('installed-probe',$Label)
 $creation=(Get-Item -LiteralPath $Source).CreationTimeUtc.ToString('o')
 $all=[IO.File]::ReadAllBytes($Source)
 if($all.Length -lt $Offset){throw 'Source log shrank; refuse shifted evidence'}
 $part=[byte[]]::new($all.Length-$Offset);[Array]::Copy($all,$Offset,$part,0,$part.Length)
 $text=[Text.Encoding]::UTF8.GetString($part)
 if($text.Contains($Secret) -or $text.Contains($WholeHandshake) -or $text.IndexOf('Authorization: Bearer',[StringComparison]::OrdinalIgnoreCase) -ge 0){throw 'Sensitive data in original log; refuse archive'}
 $snapshot=Join-Path $out ($Name+'.source-snapshot')
 if(Test-Path -LiteralPath $snapshot){throw 'Source snapshot exists'}
 [IO.File]::WriteAllBytes($snapshot,$all)
 $target=Join-Path $out $Name
 if(Test-Path -LiteralPath $target){throw 'Segment evidence exists'}
 [IO.File]::WriteAllBytes($target,$part)
 $rows=@();$offsetInPart=0;$line=1+@($all[0..([Math]::Max(0,$Offset-1))]|Where-Object {$_ -eq 10}).Count
 foreach($chunk in $text -split "(?<=`n)"){
  if(-not $chunk){continue};$bytes=[Text.Encoding]::UTF8.GetByteCount($chunk);$r=$chunk|ConvertFrom-Json
  $rows+=@([ordered]@{line=$line;byte_offset=$Offset+$offsetInPart;bytes=$bytes;timestamp=$r.timestamp;event=$r.event;pid=$r.pid})
  $offsetInPart+=$bytes;$line++
 }
 [ordered]@{source=$Source;creation_time_utc=$creation;source_snapshot=$snapshot;source_bytes=$all.Length;source_sha256=Hash-Bytes $all;byte_start=$Offset;byte_end_exclusive=$all.Length;archive=$target;archive_sha256=Hash-Bytes $part;archive_bytes=$part.Length;first_timestamp=$rows[0].timestamp;last_timestamp=$rows[-1].timestamp;records=$rows;exact_token_hits=0;whole_handshake_hits=0;authorization_bearer=$false}
}
try{
 $binding=Get-Content -LiteralPath (Join-Path $out $BindingName) -Raw|ConvertFrom-Json
 $data=$RealData
 $program=$RealProgram
 $result.lineage_before=Assert-RealLineage ($Label+'-before')
 $exe=Join-Path $program 'spectrum-agent.exe'
 if((Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant() -cne $binding.shell_sha256){throw 'Host installed shell does not match new package'}
 $related=@(Get-CimInstance Win32_Process -Filter "Name='spectrum-agent.exe' OR Name='app.exe'"|Where-Object {$_.ExecutablePath -and ($_.ExecutablePath -like '*AI_Agent*' -or $_.ExecutablePath -like '*Programs\SpectrumAgent*')})
 if($related.Count){throw 'Host related process still active'}
 $env:TEMP=Join-Path $out 'temp';$env:TMP=$env:TEMP
 $env:WEBVIEW2_USER_DATA_FOLDER=Join-Path $env:TEMP ('webview-host-installed-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ'))
 $env:SPECTRUM_ACCEPTANCE_PROBE='1'
 $env:SPECTRUM_ENGINE_EXE='E:\AI_Agent\invalid-host-installed-override\app.exe'
 $shellLog=Join-Path $data 'logs\shell-20261019.log';$engineLog=Join-Path $data 'logs\engine-20261019.jsonl'
 $shellOffset=if(Test-Path -LiteralPath $shellLog){(Get-Item -LiteralPath $shellLog).Length}else{0}
 $engineOffset=if(Test-Path -LiteralPath $engineLog){(Get-Item -LiteralPath $engineLog).Length}else{0}
 $launched=[DateTime]::UtcNow.ToString('o')
 Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class InstalledExitProbe {
 [DllImport("kernel32",SetLastError=true)] public static extern IntPtr OpenProcess(uint access,bool inherit,uint pid);
 [DllImport("kernel32",SetLastError=true)] public static extern bool GetExitCodeProcess(IntPtr process,out uint code);
 [DllImport("kernel32")] public static extern bool CloseHandle(IntPtr handle);
}
'@
 $primary=Start-Process -FilePath $exe -WorkingDirectory $env:TEMP -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $out ($Label+'.stdout.txt')) -RedirectStandardError (Join-Path $out ($Label+'.stderr.txt'))
 $processHandle=[InstalledExitProbe]::OpenProcess(0x101000,$false,$primary.Id)
 if($processHandle -eq [IntPtr]::Zero){throw 'Could not hold process query/synchronize handle'}
 $launch=[ordered]@{launch_before_utc=$launched;pid=$primary.Id;exe=$exe;shell_sha256=$binding.shell_sha256;features='custom-protocol';data_root=$data;shell_log_before_bytes=$shellOffset;engine_log_before_bytes=$engineOffset;invalid_engine_override=$env:SPECTRUM_ENGINE_EXE;uninstall_registry_before_launch=Test-Path -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SpectrumAgent'}
 Save-Json 'installed-probe-launch.json' $launch
 $identity=$null;$whole=$null;$child=$null;$deadline=[DateTime]::UtcNow.AddSeconds(30)
 while([DateTime]::UtcNow -lt $deadline -and -not $primary.HasExited){
  $children=@(Get-CimInstance Win32_Process -Filter ("ParentProcessId="+$primary.Id+" AND Name='app.exe'"))
  if($children.Count -eq 1 -and (Test-Path -LiteralPath (Join-Path $data 'run\handshake.json'))){
   $whole=[IO.File]::ReadAllText((Join-Path $data 'run\handshake.json'));$candidate=$whole|ConvertFrom-Json
   if($candidate.pid -eq $children[0].ProcessId){$identity=$candidate;$child=$children[0];break}
  }
  Start-Sleep -Milliseconds 50
 }
 if(-not $identity){throw 'Installed engine did not publish its own handshake'}
 $expectedChild=Join-Path $program 'resources\backend\app.exe'
 if($child.ExecutablePath.Replace('\\?\','') -ine $expectedChild){throw 'Installed engine path mismatch'}
 $secret=[string]$identity.token
 $redacted=$whole|ConvertFrom-Json;$redacted.token='<redacted>'
 Save-Json 'installed-probe-handshake-redacted.json' $redacted
 & C:\Windows\System32\curl.exe --noproxy '*' --silent --show-error --include ('http://127.0.0.1:'+$identity.port+'/health')|Out-File -LiteralPath (Join-Path $out ($Label+'-health-http.txt')) -Encoding utf8
 if($LASTEXITCODE -ne 0){throw 'Installed health curl failed'}
 $result.shell_pid=$primary.Id;$result.engine_pid=$identity.pid;$result.boot_id=$identity.boot_id;$result.port=$identity.port;$result.engine_path=$child.ExecutablePath;$result.shell_sha256=$binding.shell_sha256
 # A second instance has no JS input and must activate the existing window.
 $secondaryBefore=[IO.File]::ReadAllBytes((Join-Path $data 'run\handshake.json'))
 $secondary=Start-Process -FilePath $exe -WindowStyle Hidden -PassThru
 if(-not $secondary.WaitForExit(10000)){throw 'Second instance did not exit'}
 $secondAfter=[IO.File]::ReadAllBytes((Join-Path $data 'run\handshake.json'))
 $shells=@(Get-CimInstance Win32_Process -Filter "Name='spectrum-agent.exe'"|Where-Object {$_.ExecutablePath -and $_.ExecutablePath.Replace('\\?\','') -ieq $exe})
 $result.single_instance=[ordered]@{primary_pid=$primary.Id;secondary_pid=$secondary.Id;secondary_exit=$secondary.ExitCode;remaining_shells=@($shells|Select-Object ProcessId,ExecutablePath);handshake_bytes_unchanged=([Convert]::ToBase64String($secondaryBefore) -ceq [Convert]::ToBase64String($secondAfter))}
 if($secondary.ExitCode -ne 0 -or $shells.Count -ne 1 -or $shells[0].ProcessId -ne $primary.Id -or -not $result.single_instance.handshake_bytes_unchanged){throw 'Installed single instance failed'}
 $deadline=[DateTime]::UtcNow.AddMinutes(8)
 while(-not $primary.HasExited -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 100;$primary.Refresh()}
 if(-not $primary.HasExited){throw 'Installed probe not closed in8min; preserve running state'}
 $primary.WaitForExit()
 $nativeExit=[uint32]0
 if(-not [InstalledExitProbe]::GetExitCodeProcess($processHandle,[ref]$nativeExit)){throw 'Native exit code unavailable'}
 $result.shell_exit_code=$nativeExit
 $result.exit_code_source='held OpenProcess handle + GetExitCodeProcess'
 $remaining=@(Get-CimInstance Win32_Process -Filter "Name='spectrum-agent.exe' OR Name='app.exe'"|Where-Object {$_.ExecutablePath -and $_.ExecutablePath.Replace('\\?\','').StartsWith($program+'\',[StringComparison]::OrdinalIgnoreCase)}|Select-Object ProcessId,ExecutablePath)
 $result.remaining_processes=$remaining
 $result.remaining_port_listeners=@(Get-NetTCPConnection -LocalPort $identity.port -State Listen -ErrorAction SilentlyContinue).Count
 $result.handshake_exists_after_close=Test-Path -LiteralPath (Join-Path $data 'run\handshake.json')
 $result.handshake_cleanup_passed=-not $result.handshake_exists_after_close
 if($result.handshake_exists_after_close){$stale=Get-Content -LiteralPath (Join-Path $data 'run\handshake.json') -Raw|ConvertFrom-Json;$result.remaining_handshake_identity=[ordered]@{pid=$stale.pid;boot_id=$stale.boot_id;port=$stale.port};$result.remaining_handshake_pid_present=@(Get-Process -Id $stale.pid -ErrorAction SilentlyContinue).Count}
 $result.lineage_after=Assert-RealLineage ($Label+'-after')
 $result.logs=@((Copy-Segment $shellLog $shellOffset 'installed-probe-shell.jsonl' $secret $whole),(Copy-Segment $engineLog $engineOffset 'installed-probe-engine.jsonl' $secret $whole))
 $domSource=Join-Path $data ('acceptance\dom-'+$primary.Id+'.jsonl');$dom=[IO.File]::ReadAllBytes($domSource);$domText=[Text.Encoding]::UTF8.GetString($dom)
 if($domText.Contains($secret) -or $domText.Contains($whole) -or $domText.IndexOf('Authorization: Bearer',[StringComparison]::OrdinalIgnoreCase) -ge 0){throw 'Installed DOM leaked secret; do not copy'}
 $domTarget=Join-Path $out ('dom-'+$primary.Id+'.jsonl');if(Test-Path -LiteralPath $domTarget){throw 'DOM evidence exists'}
 [IO.File]::WriteAllBytes($domTarget,$dom)
 $domRows=@($domText -split "`n"|Where-Object {$_}|ForEach-Object{$_|ConvertFrom-Json});$phases=[ordered]@{}
 foreach($row in $domRows){$doc=$row.document;if($null -eq $doc.html){continue};if($doc.url -cne 'http://tauri.localhost/' -or @($doc.localStorage).Count -or @($doc.sessionStorage).Count){throw 'Installed DOM URL/storage failed'};if(-not $phases.Contains($doc.phase)){$phases[$doc.phase]=0};$phases[$doc.phase]++}
 $result.dom=[ordered]@{source=$domSource;archive=$domTarget;sha256=Hash-Bytes $dom;bytes=$dom.Length;phases=$phases;actual_token_samples=1;exact_token_hits=0;whole_handshake_hits=0;authorization_bearer=$false;localStorage_entries=0;sessionStorage_entries=0}
 $result.uninstall_registry_after_close=Test-Path -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SpectrumAgent'
 if($remaining.Count -or $result.remaining_port_listeners){throw 'Installed engine/shell orphan or port listener remains'}
 if(-not $phases.Contains('Starting') -or -not $phases.Contains('Ready') -or -not $phases.Contains('Stopping')){throw 'Installed DOM did not cover required Starting/Ready/Stopping phases'}
 $result.status='passed_process_dom_checks';$result.finished_utc=[DateTime]::UtcNow.ToString('o')
}catch{$result.status='failed';$result.error=$_.Exception.Message}finally{if($processHandle -ne [IntPtr]::Zero){[InstalledExitProbe]::CloseHandle($processHandle)|Out-Null}}
[IO.File]::WriteAllText($receipt,($result|ConvertTo-Json -Depth 18)+"`n",[Text.UTF8Encoding]::new($false))
