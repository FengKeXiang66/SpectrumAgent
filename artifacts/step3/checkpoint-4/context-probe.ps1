param([ValidateSet('tool','explorer')][string]$Label)
$ErrorActionPreference='Stop'
$env:TEMP='E:\AI_Agent\artifacts\step3\checkpoint-4\temp'
$env:TMP=$env:TEMP
Add-Type -TypeDefinition @'
using System;using System.Text;using System.Runtime.InteropServices;
public static class PackageProbe {
 [DllImport("kernel32",CharSet=CharSet.Unicode)] public static extern int GetCurrentPackageFullName(ref uint count,StringBuilder text);
}
'@
$count=[uint32]1024;$buffer=[Text.StringBuilder]::new(1024)
$code=[PackageProbe]::GetCurrentPackageFullName([ref]$count,$buffer)
$root=Join-Path $env:LOCALAPPDATA 'SpectrumAgent'
$hs=Get-Content -LiteralPath (Join-Path $root 'run\handshake.json') -Raw | ConvertFrom-Json
$hs.token='[REDACTED]'
$bytes=[IO.File]::ReadAllBytes((Join-Path $root 'logs\shell-20261018.log'))
$actual=Get-Content -LiteralPath (Join-Path $root 'run\handshake.json') -Raw | ConvertFrom-Json
if([Text.Encoding]::UTF8.GetString($bytes).Contains($actual.token)){throw 'Original source contains actual token'}
[IO.File]::WriteAllBytes("E:\AI_Agent\artifacts\step3\checkpoint-4\context-$Label-shell.log",$bytes)
$p=Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
$result=[ordered]@{label=$Label;pid=$PID;parent_pid=$p.ParentProcessId;package_api_result=$code;package=$buffer.ToString();localappdata=$env:LOCALAPPDATA;handshake=$hs;shell_log_bytes=(Get-Item -LiteralPath (Join-Path $root 'logs\shell-20261018.log')).Length;shell_log_sha256=(Get-FileHash -LiteralPath (Join-Path $root 'logs\shell-20261018.log')).Hash}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath "E:\AI_Agent\artifacts\step3\checkpoint-4\context-$Label.json" -Encoding utf8
$result | ConvertTo-Json -Depth 8
