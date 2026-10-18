param([ValidateSet('Close','KillReady','KillStarting')][string]$Mode,[int]$Rounds=10)
$ErrorActionPreference='Stop'
$PSNativeCommandUseErrorActionPreference=$false
$repo='E:\AI_Agent'
$env:TEMP=Join-Path $repo 'artifacts\step3\checkpoint-4\temp'
$env:TMP=$env:TEMP
$shellPath=Join-Path $repo 'src-tauri\target\release\spectrum-agent.exe'
$enginePath=Join-Path (Split-Path $shellPath) 'resources\backend\app.exe'
$dataRoot=Join-Path $env:LOCALAPPDATA 'SpectrumAgent'
$handshake=Join-Path $dataRoot 'run\handshake.json'
$shellLog=Join-Path $dataRoot ('logs\shell-'+(Get-Date -Format yyyyMMdd)+'.log')
$run=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'-'+$Mode
$out=Join-Path $repo ('artifacts\step3\checkpoint-4\'+$run)
New-Item -ItemType Directory -Path $out | Out-Null
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class JobProbe {
 [DllImport("kernel32",SetLastError=true)] static extern IntPtr OpenProcess(uint a,bool i,uint p);
 [DllImport("kernel32",SetLastError=true)] static extern bool IsProcessInJob(IntPtr p,IntPtr j,out bool b);
 [DllImport("kernel32")] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32",SetLastError=true,CharSet=CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr h,uint flags,System.Text.StringBuilder text,ref uint size);
 public static string ImagePath(uint pid){var h=OpenProcess(0x1000,false,pid);if(h==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();try{uint size=32768;var b=new System.Text.StringBuilder((int)size);if(!QueryFullProcessImageName(h,0,b,ref size))throw new System.ComponentModel.Win32Exception();return b.ToString();}finally{CloseHandle(h);}}
 public static bool InJob(uint pid) {var h=OpenProcess(0x1000,false,pid); if(h==IntPtr.Zero) throw new System.ComponentModel.Win32Exception(); try{bool b;if(!IsProcessInJob(h,IntPtr.Zero,out b))throw new System.ComponentModel.Win32Exception();return b;}finally{CloseHandle(h);}}
}
'@
function Normalize-Executable([string]$Path){if($Path.StartsWith('\\?\')){$Path=$Path.Substring(4)};[IO.Path]::GetFullPath($Path)}
function ProcessesAt([string]$Path){
 @(Get-CimInstance Win32_Process -Filter ("Name='"+[IO.Path]::GetFileName($Path)+"'") | ForEach-Object {
   $candidate=$_
   try{$nativePath=[JobProbe]::ImagePath($candidate.ProcessId)}catch{if(Get-Process -Id $candidate.ProcessId -ErrorAction SilentlyContinue){throw};return}
   if((Normalize-Executable $nativePath) -ieq $Path){$candidate | Add-Member -NotePropertyName NativeExecutablePath -NotePropertyValue $nativePath -PassThru}
 })
}
$handshakeSnapshots=[Collections.Generic.List[string]]::new()
function Read-Handshake {
 try {
  $stream=[IO.File]::Open($handshake,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
  try{$reader=[IO.StreamReader]::new($stream);$raw=$reader.ReadToEnd()}finally{$stream.Dispose()}
  $parsed=$raw|ConvertFrom-Json
  if($parsed.token -and -not $handshakeSnapshots.Contains($raw)){$handshakeSnapshots.Add($raw)}
  $parsed
 }catch{$null}
}
function Port-Open([int]$Port){
 if(-not $Port){return $false};$client=[Net.Sockets.TcpClient]::new()
 try{$task=$client.ConnectAsync('127.0.0.1',$Port); $null=$task.Wait(250);return $client.Connected}catch{return $false}finally{$client.Dispose()}
}
$tokens=[Collections.Generic.List[string]]::new()
$rows=[Collections.Generic.List[object]]::new()
$explorerWindows=(New-Object -ComObject Shell.Application).Windows()
if($explorerWindows.Count -lt 1){throw 'An existing Explorer window is required for an out-of-process launch broker'}
$broker=$explorerWindows.Item(0).Document.Application
$binaryHash=(Get-FileHash -LiteralPath $shellPath).Hash.ToLowerInvariant()
$global:SpectrumAcceptanceOwnedProcess=$null
for($round=1;$round -le $Rounds;$round++){
 if((ProcessesAt $shellPath).Count -or (ProcessesAt $enginePath).Count){throw 'Precondition: prior own process still running'}
 $old=Read-Handshake
 if($old.token){$tokens.Add($old.token)}
 $offset=if(Test-Path -LiteralPath $shellLog){(Get-Item -LiteralPath $shellLog).Length}else{0}
 $clock=[Diagnostics.Stopwatch]::StartNew()
 # Explorer brokers a direct executable launch; provenance and absence of a parent Job are asserted below.
 $broker.ShellExecute($shellPath,'',(Split-Path $shellPath),'open',1)
 $shell=$null;$child=$null;$current=$null;$events=@()
 while($clock.Elapsed.TotalSeconds -lt 15){
   if(-not $shell){$found=@(ProcessesAt $shellPath);if($found.Count -eq 1){$shell=$found[0];$global:SpectrumAcceptanceOwnedProcess=$shell}}
   if(Test-Path -LiteralPath $shellLog){
     $stream=[IO.File]::Open($shellLog,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
     try{$null=$stream.Seek($offset,[IO.SeekOrigin]::Begin);$reader=[IO.StreamReader]::new($stream);$text=$reader.ReadToEnd()}finally{$stream.Dispose()}
     $events=@($text -split "`n" | Where-Object {$_} | ForEach-Object {try{$_ | ConvertFrom-Json}catch{}})
   }
   $created=@($events | Where-Object {$_.event -eq 'process_identity_recorded'})
   if($created.Count){$child=$created[-1].pid}
   $current=Read-Handshake
   $published=$child -and $current -and $current.pid -eq $child
   if($Mode -eq 'KillStarting' -and $shell -and $child){break}
   if($shell -and $published -and @($events|Where-Object {$_.event -eq 'health_verified' -and $_.pid -eq $child}).Count){break}
   Start-Sleep -Milliseconds 10
 }
 if(-not $shell -or -not $child -or ($Mode -ne 'KillStarting' -and -not $published)){
   [ordered]@{diagnostic='spawn_observation_failed';shell=$shell;child=$child;data_root=$dataRoot;log_path=$shellLog;offset=$offset;event_count=$events.Count;log_bytes=(Get-Item -LiteralPath $shellLog).Length;last_events=@($events|Select-Object -Last 12)}|ConvertTo-Json -Depth 10
   throw "Round ${round}: spawn identity not observed"
 }
 $parent=Get-CimInstance Win32_Process -Filter "ProcessId=$($shell.ParentProcessId)"
 $parentPath=[JobProbe]::ImagePath($parent.ProcessId)
 $parentInJob=[JobProbe]::InJob($shell.ParentProcessId)
 if($parentPath -ine 'C:\Windows\explorer.exe' -or $parentInJob){throw "Round ${round}: Explorer parent/outside-job proof failed"}
 $engine=Get-CimInstance Win32_Process -Filter "ProcessId=$child"
 $engineNativePath=[JobProbe]::ImagePath($child)
 if((Normalize-Executable $engineNativePath) -ine $enginePath){throw "Round ${round}: child executable mismatch"}
 $port=$null;$boot=$null
 if($published){$port=$current.port;$boot=$current.boot_id;$tokens.Add($current.token)}
 if($Mode -eq 'KillStarting' -and $published){throw "Round ${round}: too late, own handshake already published; do not count"}
 if($Mode -ne 'KillStarting' -and -not $published){throw "Round ${round}: own Ready handshake absent"}
 [ordered]@{round=$round;mode=$Mode;shell_pid=$shell.ProcessId;shell_path=$shell.NativeExecutablePath;shell_cim_path=$shell.ExecutablePath;parent_pid=$parent.ProcessId;parent_path=$parentPath;parent_cim_path=$parent.ExecutablePath;parent_in_job=$parentInJob;engine_pid=$child;engine_path=$engineNativePath;engine_cim_path=$engine.ExecutablePath;port=$port;boot_id=$boot;handshake_published=$published;elapsed_ms=$clock.ElapsedMilliseconds} | ConvertTo-Json -Compress
 if($Mode -eq 'Close'){
   Write-Output "WAITING_FOR_WINDOW_CLOSE round=$round shell_pid=$($shell.ProcessId) engine_pid=$child port=$port"
   $deadline=[DateTime]::UtcNow.AddMinutes(10)
   while((Get-Process -Id $shell.ProcessId -ErrorAction SilentlyContinue) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 100}
 }else{
   if($Mode -eq 'KillStarting'){
     $lastRead=Read-Handshake
     if($lastRead -and $lastRead.pid -eq $child){throw "Round ${round}: handshake appeared before taskkill; do not count"}
   }
   & C:\Windows\System32\taskkill.exe /PID $shell.ProcessId /F | ForEach-Object {Write-Output $_}
 }
 $deadline=[DateTime]::UtcNow.AddSeconds(10)
 do{$remaining=@(ProcessesAt $enginePath);if(-not $remaining.Count){break};Start-Sleep -Milliseconds 50}while([DateTime]::UtcNow -lt $deadline)
 $shellAlive=@(ProcessesAt $shellPath).Count
 $portAlive=if($port){Port-Open $port}else{$false}
 if($remaining.Count -or $shellAlive -or $portAlive){throw "Round ${round}: cleanup failed"}
 $global:SpectrumAcceptanceOwnedProcess=$null
 if($Mode -eq 'KillStarting'){
   $afterKill=Read-Handshake
   if($afterKill -and $afterKill.pid -eq $child){throw "Round ${round}: own handshake appeared during kill; do not count"}
 }
 $row=[ordered]@{round=$round;mode=$Mode;shell_pid=$shell.ProcessId;shell_path=$shell.NativeExecutablePath;shell_cim_path=$shell.ExecutablePath;parent_pid=$parent.ProcessId;parent_path=$parentPath;parent_cim_path=$parent.ExecutablePath;parent_in_job=$parentInJob;engine_pid=$child;engine_path=$engineNativePath;engine_cim_path=$engine.ExecutablePath;port=$port;port_status=$(if($null -eq $port){'unpublished_before_kill'}else{'closed'});boot_id=$boot;old_boot_id=$old.boot_id;handshake_published_before_action=$published;engine_remaining=$remaining.Count;shell_remaining=$shellAlive;port_open=$portAlive;binary_sha256=$binaryHash;passed=$true}
 $rows.Add($row);$row | ConvertTo-Json -Compress
 $events | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath (Join-Path $out "round-$round-events.json") -Encoding utf8
}
$raw=[IO.File]::ReadAllText($shellLog)
$hits=@($tokens | Select-Object -Unique | Where-Object {$raw.Contains($_)}).Count
$bearer=$raw.IndexOf('Authorization: Bearer',[StringComparison]::OrdinalIgnoreCase) -ge 0
$wholeHandshakeHits=@($handshakeSnapshots|Where-Object {$raw.Contains($_)}).Count
if($hits -or $bearer -or $wholeHandshakeHits){throw 'Original shell log token audit failed'}
[IO.File]::WriteAllBytes((Join-Path $out 'original-shell.log'),[IO.File]::ReadAllBytes($shellLog))
$rows | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $out 'results.json') -Encoding utf8
[ordered]@{mode=$Mode;rounds=$rows.Count;actual_token_samples=@($tokens|Select-Object -Unique).Count;full_handshake_samples=$handshakeSnapshots.Count;whole_handshake_json_hits=$wholeHandshakeHits;original_source=$shellLog;exact_token_hits=$hits;authorization_bearer=$bearer;sha256=(Get-FileHash -LiteralPath $shellLog).Hash.ToLowerInvariant();binary_sha256_after=(Get-FileHash -LiteralPath $shellPath).Hash.ToLowerInvariant()} | ConvertTo-Json | Tee-Object -FilePath (Join-Path $out 'audit.json')
if((Get-FileHash -LiteralPath $shellPath).Hash.ToLowerInvariant() -cne $binaryHash){throw 'Tested binary changed during matrix'}
Write-Output "MATRIX_PASSED mode=$Mode rounds=$Rounds output=$out"
