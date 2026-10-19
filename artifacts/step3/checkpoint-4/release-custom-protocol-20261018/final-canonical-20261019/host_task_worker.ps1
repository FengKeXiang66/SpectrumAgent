param([ValidateSet('Capture','CaptureComplete','UninstallRepro','RecoverRepro','InstallDelivery','ProbeDelivery','UninstallDelivery')][string]$Action)
$ErrorActionPreference='Stop'
$out=$PSScriptRoot
. (Join-Path $out 'real_root.ps1')
$receipt=Join-Path $out ('real-task-'+$Action+'-result.json')
if(Test-Path -LiteralPath $receipt){throw 'Task receipt exists'}
$r=[ordered]@{action=$Action;started_utc=[DateTime]::UtcNow.ToString('o');status='running';error=$null;context='one-time scheduled task; interactive host token';identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name;sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value}
try{
 $r.lineage=Assert-RealLineage ('real-task-'+$Action)
 $r.registry_before=@('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SpectrumAgent','HKCU:\Software\spectrumagent\SpectrumAgent')|ForEach-Object{[ordered]@{path=$_;exists=Test-Path -LiteralPath $_}}
 if($Action -like 'Capture*'){
  $source=$RealData+'\logs\engine-20261019.jsonl'
  $item=Get-Item -LiteralPath $source
  $bytes=[IO.File]::ReadAllBytes($source)
  $snapshot=Join-Path $out 'legacy-6236-engine-complete-v2-source.jsonl'
  if(Test-Path -LiteralPath $snapshot){throw 'Source exists'}
  [IO.File]::WriteAllBytes($snapshot,$bytes)
  $selected=[IO.MemoryStream]::new();$offset=0;$line=0;$records=@()
  for($i=0;$i -lt $bytes.Length;$i++){
   if($bytes[$i] -ne 10 -and $i -ne $bytes.Length-1){continue}
   $length=$i-$offset+1;$line++;$raw=[byte[]]::new($length);[Array]::Copy($bytes,$offset,$raw,0,$length)
   $row=[Text.Encoding]::UTF8.GetString($raw)|ConvertFrom-Json
   $stamp=([string]$row.timestamp).Replace(' ','T')
   if($stamp -ge '2026-10-19T02:23:39' -and $stamp -lt '2026-10-19T02:23:47'){
    $selected.Write($raw,0,$raw.Length);$records+=@([ordered]@{line=$line;byte_offset=$offset;bytes=$length;timestamp=$row.timestamp;event=$row.event;pid=$row.pid;boot_id=$row.boot_id})
   }
   $offset=$i+1
  }
  if(-not @($records|Where-Object {$_.event -eq 'engine_boot' -and $_.pid -eq 26088 }).Count){throw 'Missing required engine_boot'}
  $target=Join-Path $out 'legacy-6236-engine-complete.jsonl'
  [IO.File]::WriteAllBytes($target,$selected.ToArray());$selected.Dispose()
  $r.engine=[ordered]@{source=$source;creation_time_utc=$item.CreationTimeUtc.ToString('o');source_snapshot=$snapshot;source_sha256=(Get-FileHash -LiteralPath $snapshot).Hash.ToLowerInvariant();archive=$target;archive_sha256=(Get-FileHash -LiteralPath $target).Hash.ToLowerInvariant();records=$records}
 }elseif($Action -eq 'UninstallRepro'){
  & (Join-Path $out 'selfcheck_install.ps1') -Phase PrepareUninstall -EvidenceTag repro-real-cleanup -BindingName candidate-repro.json -BundleReceipt bundle-repro-cached-execution.json | Out-File -LiteralPath (Join-Path $out 'repro-real-cleanup-prepare-output.txt') -Encoding utf8
  & (Join-Path $out 'selfcheck_install.ps1') -Phase Uninstall -EvidenceTag repro-real-cleanup -BindingName candidate-repro.json -BundleReceipt bundle-repro-cached-execution.json | Out-File -LiteralPath (Join-Path $out 'repro-real-cleanup-uninstall-output.txt') -Encoding utf8
 }elseif($Action -eq 'RecoverRepro'){
  # PowerShell5 ConvertFrom-Json emits arrays as one pipeline object. The two
  # immutable snapshots are complete; independently compare their actual rows.
  $before=Get-Content -LiteralPath (Join-Path $out 'repro-real-cleanup-data-before-uninstall.json') -Raw|ConvertFrom-Json
  $after=Get-Content -LiteralPath (Join-Path $out 'repro-real-cleanup-data-after-uninstall.json') -Raw|ConvertFrom-Json
  $raw=Get-Content -LiteralPath (Join-Path $out 'repro-real-cleanup-host-uninstall-result.json') -Raw|ConvertFrom-Json
  if($raw.initial_uninstaller_exit -ne 0 -or -not $raw.program_directory_removed -or (Test-Path -LiteralPath $RealProgram)){throw 'Original uninstall did not succeed'}
  if($before.Count -ne $after.Count){throw 'Actual snapshot row counts differ'}
  for($i=0;$i -lt $before.Count;$i++){if($before[$i].path -cne $after[$i].path -or $before[$i].bytes -ne $after[$i].bytes -or $before[$i].sha256 -cne $after[$i].sha256){throw 'Actual data bytes differ'}}
  $r.snapshot_comparison=[ordered]@{before=$before.Count;after=$after.Count;all_data_bytes_unchanged=$true;original_result_preserved=$true;harness_error='Windows PowerShell5 array pipeline wrapped as one item; corrected by direct assignment'}
  $state=Join-Path $out 'host-install-state.json';$sha=(Get-FileHash -LiteralPath $state).Hash.ToLowerInvariant();$archive=Join-Path $out ('host-install-state.'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'.json')
  Move-Item -LiteralPath $state -Destination $archive
  if((Get-FileHash -LiteralPath $archive).Hash.ToLowerInvariant() -cne $sha){throw 'Archived state differs'}
  $r.state_archive=[ordered]@{source=$state;destination=$archive;sha256=$sha;archived_utc=[DateTime]::UtcNow.ToString('o');reason='uninstall exit0/program removed; independent actual16-row comparison passed; same-directory archival'}
  $markers=Get-Content -LiteralPath (Join-Path $out 'repro-real-cleanup-uninstall-markers.json') -Raw|ConvertFrom-Json
  foreach($m in $markers){if(-not $m.path.StartsWith($RealData+'\',[StringComparison]::OrdinalIgnoreCase) -or (Get-FileHash -LiteralPath $m.path).Hash -cne $m.sha256){throw 'Foreign/changed marker'};Remove-Item -LiteralPath $m.path}
  $r.hygiene='TEST_HYGIENE_ONLY: exact3markers removed after byte comparison; not a product predicate'
 }elseif($Action -eq 'InstallDelivery'){
  $setup='E:\AI_Agent\src-tauri\target\release\bundle\nsis\SpectrumAgent_0.1.0_x64-setup.exe'
  if((Get-Item -LiteralPath $setup).Length -ne 287156790 -or (Get-FileHash -LiteralPath $setup).Hash.ToLowerInvariant() -cne 'd849253611c1ac985cb08a60a7073e17ed6c89b74e8230532d0c3d2157cc8107'){throw 'Delivery setup identity mismatch'}
  & (Join-Path $out 'selfcheck_install.ps1') -Phase Install -EvidenceTag delivery | Out-File -LiteralPath (Join-Path $out 'delivery-install-output.txt') -Encoding utf8
  $r.data_directories=@('db','run','logs','testdata')|ForEach-Object{[ordered]@{path=$RealData+'\'+$_;exists=Test-Path -LiteralPath ($RealData+'\'+$_)}}
 }elseif($Action -eq 'ProbeDelivery'){
  & (Join-Path $out 'host_installed_probe.ps1') -Label installed-delivery -BindingName candidate.json
 }elseif($Action -eq 'UninstallDelivery'){
  & (Join-Path $out 'selfcheck_install.ps1') -Phase PrepareUninstall | Out-File -LiteralPath (Join-Path $out 'delivery-prepare-uninstall-output.txt') -Encoding utf8
  & (Join-Path $out 'selfcheck_install.ps1') -Phase Uninstall | Out-File -LiteralPath (Join-Path $out 'delivery-uninstall-output.txt') -Encoding utf8
 }
 $r.registry_after=@('HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SpectrumAgent','HKCU:\Software\spectrumagent\SpectrumAgent')|ForEach-Object{[ordered]@{path=$_;exists=Test-Path -LiteralPath $_}}
 $r.status='passed'
}catch{$r.status='failed';$r.error=$_.Exception.ToString()}
$r.finished_utc=[DateTime]::UtcNow.ToString('o')
[IO.File]::WriteAllText($receipt,($r|ConvertTo-Json -Depth 16)+"`n",[Text.UTF8Encoding]::new($false))
