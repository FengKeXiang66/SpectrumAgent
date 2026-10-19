param([Parameter(Mandatory=$true)][ValidateSet('Install','PrepareUninstall','Uninstall')][string]$Phase)
$ErrorActionPreference='Stop'
$root='E:\AI_Agent'
$out=$PSScriptRoot
$program=Join-Path $env:LOCALAPPDATA 'Programs\SpectrumAgent'
$data=Join-Path $env:LOCALAPPDATA 'SpectrumAgent'
$stateFile=Join-Path $out 'host-install-state.json'
$beforeFile=Join-Path $out 'data-before-uninstall.json'
$key='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\SpectrumAgent'
$binding=Get-Content -LiteralPath (Join-Path $out 'candidate.json') -Raw|ConvertFrom-Json
function Write-Record([string]$Name,$Value){
 $target=Join-Path $out $Name
 if(Test-Path -LiteralPath $target){throw "Do not overwrite evidence: $target"}
 $Value|ConvertTo-Json -Depth 10|Tee-Object -FilePath $target
}
function Snapshot-Data {
 @(Get-ChildItem -LiteralPath $data -Recurse -File|Sort-Object FullName|ForEach-Object {
  [ordered]@{path=$_.FullName.Substring($data.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash}
 })
}
function Assert-NoInstalledProcesses {
 $owned=@(Get-CimInstance Win32_Process -Filter "Name='spectrum-agent.exe' OR Name='app.exe'"|Where-Object {$_.ExecutablePath -and $_.ExecutablePath.Replace('\\?\','').StartsWith($program+'\',[StringComparison]::OrdinalIgnoreCase)})
 if($owned.Count){throw 'Installed application/engine still running; close it first'}
}
if($Phase -eq 'Install'){
 if((Test-Path -LiteralPath $stateFile) -or (Test-Path -LiteralPath $program) -or (Test-Path -LiteralPath $key) -or (Test-Path -LiteralPath 'HKCU:\Software\spectrumagent\SpectrumAgent')){throw 'Unknown existing installation/state; refuse overwrite'}
 $setup=Join-Path $root 'src-tauri\target\release\bundle\nsis\SpectrumAgent_0.1.0_x64-setup.exe'
 $setupHash=(Get-FileHash -LiteralPath $setup).Hash
 $bundle=Get-Content -LiteralPath (Join-Path $out 'bundle-idle-execution.json') -Raw|ConvertFrom-Json
 if($bundle.exit_code -ne 0 -or $bundle.shell_sha256.ToLowerInvariant() -cne $binding.shell_sha256 -or $setupHash -cne $bundle.setup_sha256){throw 'Successful bundle receipt/candidate/setup mismatch'}
 $env:TEMP=Join-Path $out 'temp';$env:TMP=$env:TEMP
 $process=Start-Process -FilePath $setup -ArgumentList '/S' -WindowStyle Hidden -Wait -PassThru
 if($process.ExitCode -ne 0){throw "Installer exit=$($process.ExitCode)"}
 $main=Join-Path $program 'spectrum-agent.exe'
 if(-not (Test-Path -LiteralPath $main)){throw 'Default program path missing'}
 $registry=Get-ItemProperty -LiteralPath $key
 $location=$registry.InstallLocation.Trim('"')
 if($location -ine $program){throw "Unexpected InstallLocation: $location"}
 if((Get-FileHash -LiteralPath $main).Hash.ToLowerInvariant() -cne $binding.shell_sha256){throw 'Installed shell SHA differs'}
 Write-Record 'host-install-state.json' ([ordered]@{scope='host installation only; VM installation remains pending';installed_utc=[DateTime]::UtcNow.ToString('o');setup=$setup;setup_sha256=$setupHash;installer_pid=$process.Id;installer_exit=$process.ExitCode;program=$program;data=$data;registry_key=$key;registry_install_location=$registry.InstallLocation;shell_sha256=$binding.shell_sha256;features='custom-protocol';install_mode='currentUser';admin_requirement_test='NSIS RequestExecutionLevel user; standard-user VM test still pending'})
}elseif($Phase -eq 'PrepareUninstall'){
 $state=Get-Content -LiteralPath $stateFile -Raw|ConvertFrom-Json
 if($state.program -ine $program -or $state.data -ine $data){throw 'Installation state/path mismatch'}
 Assert-NoInstalledProcesses
 $id=[guid]::NewGuid().ToString('D');$markers=@()
 foreach($folder in @('run','logs','testdata')){
  $directory=Join-Path $data $folder
  if(-not (Test-Path -LiteralPath $directory)){throw "Data directory missing: $directory"}
  $file=Join-Path $directory ('uninstall-preservation-'+$id+'.txt')
  [IO.File]::WriteAllText($file,'Owned acceptance marker '+$id,[Text.UTF8Encoding]::new($false))
  $markers+=@([ordered]@{path=$file;sha256=(Get-FileHash -LiteralPath $file).Hash})
 }
 Write-Record 'uninstall-markers.json' $markers
 Write-Record 'data-before-uninstall.json' (Snapshot-Data)
}else{
 $state=Get-Content -LiteralPath $stateFile -Raw|ConvertFrom-Json
 if($state.program -ine $program -or $state.data -ine $data){throw 'Installation state/path mismatch'}
 if(-not ([IO.Path]::GetFullPath($program)).StartsWith(([IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs')))+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Program target outside intended parent'}
 Assert-NoInstalledProcesses
 $uninstaller=Join-Path $program 'uninstall.exe'
 $uninstallerHash=(Get-FileHash -LiteralPath $uninstaller).Hash
 $before=@(Get-Content -LiteralPath $beforeFile -Raw|ConvertFrom-Json)
 $process=Start-Process -FilePath $uninstaller -ArgumentList '/S' -WindowStyle Hidden -Wait -PassThru
 $deadline=[DateTime]::UtcNow.AddSeconds(30)
 while((Test-Path -LiteralPath $program) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 100}
 $removed=-not (Test-Path -LiteralPath $program)
 $after=Snapshot-Data
 Write-Record 'data-after-uninstall.json' $after
 $beforeMap=@{};foreach($r in $before){$beforeMap[$r.path]=[string]$r.bytes+':'+$r.sha256}
 $afterMap=@{};foreach($r in $after){$afterMap[$r.path]=[string]$r.bytes+':'+$r.sha256}
 $same=$beforeMap.Count -eq $afterMap.Count
 foreach($name in $beforeMap.Keys){if(-not $afterMap.ContainsKey($name) -or $afterMap[$name] -cne $beforeMap[$name]){$same=$false}}
 $directories=[ordered]@{};foreach($folder in @('run','logs','testdata')){$directories[$folder]=Test-Path -LiteralPath (Join-Path $data $folder)}
 Write-Record 'host-uninstall-result.json' ([ordered]@{scope='host only; VM uninstall remains pending';uninstaller_pid=$process.Id;initial_uninstaller_exit=$process.ExitCode;uninstaller_sha256=$uninstallerHash;program=$program;program_directory_removed=$removed;data=$data;data_directory_preserved=Test-Path -LiteralPath $data;data_files_before=$beforeMap.Count;data_files_after=$afterMap.Count;all_data_bytes_unchanged=$same;directories_preserved=$directories;test_hygiene_not_yet_applied=$true})
 if($process.ExitCode -ne 0 -or -not $removed -or -not $same){throw 'Uninstall acceptance failed before hygiene; preserve evidence'}
 foreach($marker in @(Get-Content -LiteralPath (Join-Path $out 'uninstall-markers.json') -Raw|ConvertFrom-Json)){
  $resolved=[IO.Path]::GetFullPath($marker.path)
  if(-not $resolved.StartsWith($data+'\',[StringComparison]::OrdinalIgnoreCase) -or (Get-FileHash -LiteralPath $resolved).Hash -cne $marker.sha256){throw 'Refuse deleting changed/foreign marker'}
  Remove-Item -LiteralPath $resolved
 }
 Write-Output 'TEST_HYGIENE_ONLY: removed three exact owned markers after successful comparison; not a product predicate'
}
