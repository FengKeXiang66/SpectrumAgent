param(
    [ValidateSet('Canonical','FaultFixture')][string]$Mode='Canonical',
    [string]$Source,
    [string]$Manifest
)
$ErrorActionPreference='Stop'
$repo=[IO.Path]::GetFullPath($PSScriptRoot)
if(-not $Manifest){$Manifest=Join-Path $repo 'artifacts\step2\revision-20261018-smoke-headers\product-manifest.json'}
$authority=Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
if(-not $Source){$Source=Join-Path $repo $authority.artifact_root}
$sourceRoot=(Resolve-Path -LiteralPath $Source).ProviderPath
$target=[IO.Path]::GetFullPath((Join-Path $repo 'src-tauri\resources\backend'))
$expectedTarget=$repo.TrimEnd('\')+'\src-tauri\resources\backend'
if($target -cne $expectedTarget -or -not $target.StartsWith($repo+'\',[StringComparison]::OrdinalIgnoreCase)){throw '目标越出工作区，拒绝暂存'}
if($sourceRoot.StartsWith((Join-Path $repo 'src-tauri\resources'),[StringComparison]::OrdinalIgnoreCase)){throw '来源不得位于暂存目标或其父目录'}
foreach($parent in @($repo,(Join-Path $repo 'src-tauri'),(Join-Path $repo 'src-tauri\resources'),$target)){
    if((Test-Path -LiteralPath $parent) -and ((Get-Item -LiteralPath $parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw "路径含重解析点：$parent"}
}
function Get-Tree([string]$Root){
    $rows=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
    foreach($item in Get-ChildItem -LiteralPath $Root -Recurse -Force){
        if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw "拒绝重解析点：$($item.FullName)"}
        if(-not $item.PSIsContainer){
            $relative=[IO.Path]::GetRelativePath($Root,$item.FullName).Replace('\','/')
            $rows.Add($relative,[ordered]@{path=$relative;bytes=$item.Length;sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()})
        }
    }
    return ,$rows
}
$wanted=[Collections.Generic.Dictionary[string,object]]::new([StringComparer]::Ordinal)
foreach($row in $authority.files){$wanted.Add($row.path,$row)}
$missingDll='_internal/python312.dll'
if($Mode -eq 'FaultFixture'){
    if(-not $wanted.Remove($missingDll)){throw '权威 manifest 缺预定 DLL，拒绝故障模式'}
}
$before=Get-Tree $sourceRoot
if($before.Count -ne $wanted.Count){throw "来源文件数不符：actual=$($before.Count) expected=$($wanted.Count) mode=$Mode"}
foreach($key in $wanted.Keys){
    if(-not $before.ContainsKey($key)){throw "来源缺文件：$key"}
    if($before[$key].bytes -ne $wanted[$key].bytes -or $before[$key].sha256 -cne $wanted[$key].sha256){throw "来源内容不符：$key"}
}
if(-not $before.ContainsKey('app.exe')){throw '来源缺 app.exe'}
Write-Output "validated_absolute_target=$target source=$sourceRoot mode=$Mode"
if(Test-Path -LiteralPath $target){Remove-Item -LiteralPath $target -Recurse -Force}
New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach($item in Get-ChildItem -LiteralPath $sourceRoot -Force){Copy-Item -LiteralPath $item.FullName -Destination $target -Recurse -Force}
$after=Get-Tree $target
$sourceAfter=Get-Tree $sourceRoot
if($after.Count -ne $before.Count -or $sourceAfter.Count -ne $before.Count){throw '复制后目录文件数不符'}
foreach($key in $before.Keys){
    foreach($tree in @($after,$sourceAfter)){
        if(-not $tree.ContainsKey($key) -or $tree[$key].bytes -ne $before[$key].bytes -or $tree[$key].sha256 -cne $before[$key].sha256){throw "复制后逐文件比对失败：$key"}
    }
}
$keys=[string[]]@($before.Keys); [Array]::Sort($keys,[StringComparer]::Ordinal)
$run=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'-'+$Mode+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$report=Join-Path $repo ('artifacts\step3\staging-reports\'+$run+'.json')
New-Item -ItemType Directory -Path (Split-Path -Parent $report) -Force | Out-Null
$record=[ordered]@{run_id=$run;mode=$Mode;fault_fixture=($Mode -eq 'FaultFixture');manifest=[IO.Path]::GetFullPath($Manifest);manifest_sha256=(Get-FileHash -LiteralPath $Manifest -Algorithm SHA256).Hash.ToLowerInvariant();artifact_source_commit=$authority.artifact_source_commit;source=$sourceRoot;target=$target;matched_files=$before.Count;source_unchanged=$true;files=@($keys | ForEach-Object {$before[$_]})}
$bytes=[Text.UTF8Encoding]::new($false).GetBytes(($record | ConvertTo-Json -Depth 8)+"`n")
$stream=[IO.File]::Open($report,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write)
try{$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}
Write-Output "report=$report matched_files=$($before.Count) fault_fixture=$($record.fault_fixture) source_unchanged=true"
