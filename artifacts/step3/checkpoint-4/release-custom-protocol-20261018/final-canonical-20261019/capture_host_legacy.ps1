$ErrorActionPreference='Stop'
$out=$PSScriptRoot
$receipt=Join-Path $out 'host-legacy-capture-receipt.json'
$result=[ordered]@{status='running';checked_utc=[DateTime]::UtcNow.ToString('o');error=$null}
try{
 $active=@(Get-CimInstance Win32_Process -Filter "Name='spectrum-agent.exe' OR Name='app.exe'"|Where-Object {$_.ExecutablePath -and ($_.ExecutablePath -like '*AI_Agent*' -or $_.ExecutablePath -like '*Programs\SpectrumAgent*')}|Select-Object ProcessId,ExecutablePath)
 if($active.Count){throw 'Host related processes are active; no capture allowed'}
 $data=Join-Path $env:LOCALAPPDATA 'SpectrumAgent'
 $program=Join-Path $env:LOCALAPPDATA 'Programs\SpectrumAgent'
 $records=@()
 foreach($role in @('shell','engine')){
  $source=Join-Path $data $(if($role -eq 'shell'){'logs\shell-20261019.log'}else{'logs\engine-20261019.jsonl'})
  $bytes=[IO.File]::ReadAllBytes($source)
  $items=@();$offset=0;$line=0
  for($i=0;$i -lt $bytes.Length;$i++){
   if($bytes[$i] -ne 10 -and $i -ne $bytes.Length-1){continue}
   $length=$i-$offset+1;$line++
   $raw=[byte[]]::new($length);[Array]::Copy($bytes,$offset,$raw,0,$length)
   $row=[Text.Encoding]::UTF8.GetString($raw)|ConvertFrom-Json
   $selected=if($role -eq 'shell'){$line -ge 531 -and $line -le 555}else{
    $row.pid -eq 26088 -and $row.boot_id -ceq '11222372' -and
    [DateTimeOffset]::Parse($row.timestamp) -ge [DateTimeOffset]::Parse('2026-10-19T02:23:38.992Z') -and
    [DateTimeOffset]::Parse($row.timestamp) -le [DateTimeOffset]::Parse('2026-10-19T02:23:47.936Z')
   }
   if($selected){$items+=@([pscustomobject]@{line=$line;offset=$offset;length=$length;row=$row;raw=$raw})}
   $offset=$i+1
  }
  if(-not $items.Count){throw "No selected $role records"}
  if($role -eq 'shell'){
   if($items.Count -ne 25 -or -not @($items|Where-Object {$_.row.event -eq 'shell_started' -and $_.row.pid -eq 6236}).Count){throw 'Host shell lines 531-555 do not identify6236'}
  }
  $target=Join-Path $out ('legacy-6236-'+$role+'.jsonl')
  if(Test-Path -LiteralPath $target){throw 'Legacy evidence already exists; never overwrite'}
  $buffer=[IO.MemoryStream]::new()
  try{foreach($item in $items){$buffer.Write($item.raw,0,$item.raw.Length)};[IO.File]::WriteAllBytes($target,$buffer.ToArray())}finally{$buffer.Dispose()}
  $records+=@([ordered]@{source=$source;source_bytes=$bytes.Length;source_sha256=(Get-FileHash -LiteralPath $source).Hash.ToLowerInvariant();archive=$target;archive_bytes=(Get-Item -LiteralPath $target).Length;archive_sha256=(Get-FileHash -LiteralPath $target).Hash.ToLowerInvariant();first_timestamp=$items[0].row.timestamp;last_timestamp=$items[-1].row.timestamp;lines=@($items|ForEach-Object{[ordered]@{line=$_.line;byte_offset=$_.offset;bytes=$_.length}})})
 }
 $keys=@('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SpectrumAgent','HKCU:\Software\spectrumagent\SpectrumAgent')
 $result.status='passed';$result.context='existing Explorer broker -> Windows PowerShell host process';$result.related_processes=$active;$result.program=$program;$result.installed_shell_sha256=(Get-FileHash -LiteralPath (Join-Path $program 'spectrum-agent.exe')).Hash.ToLowerInvariant();$result.uninstaller_exists=Test-Path -LiteralPath (Join-Path $program 'uninstall.exe');$result.registry_keys=@($keys|ForEach-Object{[ordered]@{path=$_;exists=Test-Path -LiteralPath $_}});$result.records=$records
}catch{$result.status='failed';$result.error=$_.Exception.Message}
[IO.File]::WriteAllText($receipt,($result|ConvertTo-Json -Depth 12)+"`n",[Text.UTF8Encoding]::new($false))
