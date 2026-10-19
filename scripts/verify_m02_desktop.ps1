param([int]$WaitSeconds=600)
$ErrorActionPreference='Stop'
$root='E:\AI_Agent'
$exe=Join-Path $root 'src-tauri\target\milestone02\debug\spectrum-agent.exe'
$evidence=Join-Path $root 'src-python\tests\evidence\desktop'
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
if (Get-Process -Name spectrum-agent -ErrorAction SilentlyContinue) {throw '已有外壳运行，停止以免混淆实例；不终止其它进程。'}
$env:LOCALAPPDATA=Join-Path $root '.runtime\m02-desktop'
$env:TEMP=Join-Path $root '.runtime\milestone02-temp'
$env:TMP=$env:TEMP
$env:SPECTRUM_ACCEPTANCE_PROBE='1'
Remove-Item Env:SPECTRUM_ENGINE_EXE -ErrorAction SilentlyContinue
$data=Join-Path $env:LOCALAPPDATA 'SpectrumAgent'
$started=[DateTime]::UtcNow
$process=Start-Process -FilePath $exe -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $evidence 'stderr.txt') -RedirectStandardOutput (Join-Path $evidence 'stdout.txt')
$deadline=[DateTime]::UtcNow.AddSeconds(25)
$ident=$null
$launcher=$null
while ([DateTime]::UtcNow -lt $deadline) {
    if ($process.HasExited) {throw "外壳提前退出：$($process.ExitCode)"}
    $log=Join-Path $data ('logs\shell-'+(Get-Date -Format yyyyMMdd)+'.log')
    if (Test-Path -LiteralPath $log) {
        $event=Get-Content -LiteralPath $log | ForEach-Object {$_ | ConvertFrom-Json} | Where-Object {$_.event -eq 'dev_python_identity_verified' -and [DateTime]$_.timestamp -ge $started} | Select-Object -Last 1
        if ($event) {
            $launcher=[int]$event.launcher_pid
            $ident=Get-Content -LiteralPath (Join-Path $data 'run\handshake.json') -Raw | ConvertFrom-Json
            break
        }
    }
    Start-Sleep -Milliseconds 100
}
if (!$ident) {throw '25秒内未就绪；本次未执行UI验收。'}
[pscustomobject]@{shell_pid=$process.Id;launcher_pid=$launcher;python_pid=$ident.pid;boot_id=$ident.boot_id;port=$ident.port;data_root=$data;binary=$exe;binary_sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant();started_utc=$started.ToString('o')} | ConvertTo-Json | Tee-Object (Join-Path $evidence 'run.json')
if (!$process.WaitForExit($WaitSeconds*1000)) {throw '等待人工UI验收关闭超时；未强杀、未删除握手，不记通过。'}
$ended=[DateTime]::UtcNow
# Observe before this host script exits: an outer tool Job cannot supply cleanup evidence.
$survivors=@()
foreach ($checkPid in @($launcher,[int]$ident.pid)) {
    $until=[DateTime]::UtcNow.AddSeconds(5)
    while ((Get-Process -Id $checkPid -ErrorAction SilentlyContinue) -and [DateTime]::UtcNow -lt $until) {Start-Sleep -Milliseconds 50}
    if (Get-Process -Id $checkPid -ErrorAction SilentlyContinue) {$survivors+=$checkPid}
}
$receipt=[pscustomobject]@{shell_pid=$process.Id;shell_exit=$process.ExitCode;launcher_pid=$launcher;python_pid=$ident.pid;survivors=$survivors;handshake_remaining=(Test-Path -LiteralPath (Join-Path $data 'run\handshake.json'));script_removed_handshake=$false;ended_utc=$ended.ToString('o');observed_before_host_script_exit=$true}
$receipt | ConvertTo-Json | Tee-Object (Join-Path $evidence 'close-receipt.json')
foreach ($folder in @('logs','acceptance')) {
    foreach ($file in Get-ChildItem -LiteralPath (Join-Path $data $folder) -File -ErrorAction SilentlyContinue) {
        $content=[System.IO.File]::ReadAllText($file.FullName)
        if ($content.Contains($ident.token)) {throw "凭证泄漏，拒绝归档：$($file.Name)"}
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $evidence $file.Name)
    }
}
if ($survivors.Count -ne 0 -or $process.ExitCode -ne 0) {throw '关窗后有残留进程或外壳异常退出；见close-receipt.json。'}
'DESKTOP_CLOSE PASS (handshake status reported separately; no script deletion)'
