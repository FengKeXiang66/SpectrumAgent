<#
  collect-vm-evidence.ps1
  SpectrumAgent checkpoint-4 VM acceptance: READ-ONLY evidence collector.

  DESIGN RULES (do not change without the owner's sign-off):
    * Pure ASCII. PowerShell 5.1 on zh-CN reads .ps1 as GBK; any non-ASCII
      character in this file risks corruption. Keep it ASCII.
    * COLLECT ONLY. No pass/fail judgement, no assertions, no thresholds.
      The reviewer reads the raw values and signs the verdict.
    * NEVER overwrite. Every run writes a new timestamped folder.
    * Distinguish "key absent" from "cannot read". Both are recorded verbatim.
    * No network, no external module, no admin strictly required
      (admin recommended so that ACL-restricted reads are not misread as absent).

  RUN INSIDE THE GUEST VM:
    powershell -ExecutionPolicy Bypass -File C:\Users\Public\Desktop\collect-vm-evidence.ps1 -Phase install

  Phases: install | firstrun | reboot | uninstall | manual
  Output: C:\vm-evidence\<phase>-<UTC stamp>\
#>

param(
    [ValidateSet('install','firstrun','reboot','uninstall','manual')]
    [string]$Phase = 'manual',
    [string]$OutRoot = 'C:\vm-evidence'
)

$ErrorActionPreference = 'Continue'

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$out   = Join-Path $OutRoot ("{0}-{1}" -f $Phase, $stamp)
New-Item -ItemType Directory -Path $out -Force | Out-Null

$logPath = Join-Path $out 'transcript.txt'
try { Start-Transcript -Path $logPath -Force | Out-Null } catch { }

function Sec([string]$t) {
    Write-Output ''
    Write-Output ('===== ' + $t + ' =====')
}
function Save([string]$name, $obj) {
    $p = Join-Path $out $name
    $obj | ConvertTo-Json -Depth 6 | Out-File -FilePath $p -Encoding UTF8
    Write-Output ('[saved] ' + $p)
}

$LA = $env:LOCALAPPDATA
$DATA_ROOT = Join-Path $LA 'SpectrumAgent'
$APP_ROOT  = Join-Path $LA 'Programs\SpectrumAgent'
$UNINST    = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\SpectrumAgent'
$MANUKEY   = 'Software\spectrumagent\SpectrumAgent'
$WV2_APPID = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'

# ---------------------------------------------------------------- 0. context
Sec 'CONTEXT'
$os  = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$isAdmin = $false
try {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} catch { }
$ctx = [pscustomobject]@{
    phase          = $Phase
    utc_stamp      = $stamp
    local_time     = (Get-Date).ToString('o')
    computer       = $env:COMPUTERNAME
    user           = ('{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME)
    os_caption     = $os.Caption
    os_build       = $os.BuildNumber
    ps_version     = $PSVersionTable.PSVersion.ToString()
    is_admin       = $isAdmin
    localappdata   = $LA
    data_root      = $DATA_ROOT
    app_root       = $APP_ROOT
    script_version = '1.0.0'
}
Save 'context.json' $ctx

# ------------------------------------------------- 1. uninstall registry key
Sec 'REGISTRY / UNINSTALL KEY (three hives/views)'
$regRows = @()
$targets = @(
    @{ Hive = 'HKCU'; Path = ('HKCU:\' + $UNINST) },
    @{ Hive = 'HKCU-WOW6432'; Path = ('HKCU:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\SpectrumAgent') },
    @{ Hive = 'HKLM'; Path = ('HKLM:\' + $UNINST) },
    @{ Hive = 'HKLM-WOW6432'; Path = ('HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\SpectrumAgent') }
)
foreach ($t in $targets) {
    $row = [pscustomobject]@{
        hive       = $t.Hive
        path       = $t.Path
        exists     = $false
        read_error = $null
        values     = $null
    }
    try {
        if (Test-Path -LiteralPath $t.Path) {
            $row.exists = $true
            $props = Get-ItemProperty -LiteralPath $t.Path -ErrorAction Stop
            $vals = [ordered]@{}
            foreach ($p in $props.PSObject.Properties) {
                if ($p.Name -notlike 'PS*') { $vals[$p.Name] = $p.Value }
            }
            $row.values = $vals
        }
    } catch {
        $row.read_error = $_.Exception.Message
    }
    $regRows += $row
    Write-Output ('[{0}] exists={1} error={2}' -f $t.Hive, $row.exists, $row.read_error)
    if ($row.values) { $row.values | Format-List | Out-String | Write-Output }
}
Save 'registry-uninstall.json' $regRows

# ---------------------------------------------------- 2. memory key (Tauri 2 NSIS installer MANUPRODUCTKEY - standard behavior, MUST exist after pure install)
Sec 'REGISTRY / MEMORY KEY (Tauri NSIS standard: expected PRESENT, values = INSTDIR + Installer Language=1033)'
$mkRows = @()
foreach ($t in @(
    @{ Hive='HKCU'; Path=('HKCU:\' + $MANUKEY) },
    @{ Hive='HKLM'; Path=('HKLM:\' + $MANUKEY) }
)) {
    $row = [pscustomobject]@{ hive=$t.Hive; path=$t.Path; exists=$false; read_error=$null; values=$null }
    try {
        if (Test-Path -LiteralPath $t.Path) {
            $row.exists = $true
            $props = Get-ItemProperty -LiteralPath $t.Path -ErrorAction Stop
            $vals = [ordered]@{}
            foreach ($p in $props.PSObject.Properties) {
                if ($p.Name -notlike 'PS*') { $vals[$p.Name] = $p.Value }
            }
            $row.values = $vals
        }
    } catch { $row.read_error = $_.Exception.Message }
    $mkRows += $row
    Write-Output ('[{0}] {1} exists={2}' -f $t.Hive, $t.Path, $row.exists)
}
Save 'registry-memory-key.json' $mkRows

# ------------------------------------------------------- 3. installed layout
Sec 'INSTALLED LAYOUT (app root)'
$appInfo = [pscustomobject]@{
    path   = $APP_ROOT
    exists = (Test-Path -LiteralPath $APP_ROOT)
    files  = @()
}
if ($appInfo.exists) {
    $appInfo.files = Get-ChildItem -LiteralPath $APP_ROOT -Recurse -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            [pscustomobject]@{
                rel     = $_.FullName.Substring($APP_ROOT.Length).TrimStart('\')
                bytes   = $_.Length
                mtime   = $_.LastWriteTime.ToString('o')
            }
        }
}
Write-Output ('app_root exists={0} files={1}' -f $appInfo.exists, $appInfo.files.Count)
Save 'install-layout.json' $appInfo

# also record whether the old/shared location exists (should NOT be used)
$legacy = Join-Path $env:ProgramFiles 'SpectrumAgent'
Write-Output ('legacy ProgramFiles\SpectrumAgent exists={0}' -f (Test-Path -LiteralPath $legacy))

# --------------------------------------------------------------- 4. data root
Sec 'DATA ROOT (files + SHA256)'
$dataInfo = [pscustomobject]@{
    path   = $DATA_ROOT
    exists = (Test-Path -LiteralPath $DATA_ROOT)
    files  = @()
    dirs   = @()
}
if ($dataInfo.exists) {
    $dataInfo.dirs = Get-ChildItem -LiteralPath $DATA_ROOT -Recurse -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName.Substring($DATA_ROOT.Length).TrimStart('\') }
    $dataInfo.files = Get-ChildItem -LiteralPath $DATA_ROOT -Recurse -File -ErrorAction SilentlyContinue |
        ForEach-Object {
            $h = $null
            try { $h = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256 -ErrorAction Stop).Hash } catch { }
            [pscustomobject]@{
                rel    = $_.FullName.Substring($DATA_ROOT.Length).TrimStart('\')
                bytes  = $_.Length
                mtime  = $_.LastWriteTime.ToString('o')
                sha256 = $h
            }
        }
}
Write-Output ('data_root exists={0} files={1} dirs={2}' -f $dataInfo.exists, $dataInfo.files.Count, $dataInfo.dirs.Count)
Save 'data-root.json' $dataInfo

# ------------------------------------------------------ 5. handshake lifecycle
Sec 'HANDSHAKE FILE'
$hsPath = Join-Path $DATA_ROOT 'run\handshake.json'
$hs = [pscustomobject]@{
    path        = $hsPath
    exists      = (Test-Path -LiteralPath $hsPath)
    bytes       = $null
    mtime       = $null
    content_raw = $null
    parsed      = $null
    pid_alive   = $null
    port_open   = $null
}
if ($hs.exists) {
    $f = Get-Item -LiteralPath $hsPath
    $hs.bytes = $f.Length
    $hs.mtime = $f.LastWriteTime.ToString('o')
    try {
        $hs.content_raw = Get-Content -LiteralPath $hsPath -Raw -ErrorAction Stop
        $hs.parsed = $hs.content_raw | ConvertFrom-Json
    } catch {
        Write-Output ('handshake parse failed: ' + $_.Exception.Message)
    }
    if ($hs.parsed) {
        try {
            $proc = Get-Process -Id ([int]$hs.parsed.pid) -ErrorAction Stop
            $hs.pid_alive = $true
            Write-Output ('handshake pid {0} ALIVE name={1}' -f $hs.parsed.pid, $proc.ProcessName)
        } catch {
            $hs.pid_alive = $false
            Write-Output ('handshake pid {0} NOT alive' -f $hs.parsed.pid)
        }
        try {
            $c = New-Object Net.Sockets.TcpClient
            $iar = $c.BeginConnect('127.0.0.1', [int]$hs.parsed.port, $null, $null)
            $hs.port_open = $iar.AsyncWaitHandle.WaitOne(700)
            $c.Close()
            Write-Output ('handshake port {0} open={1}' -f $hs.parsed.port, $hs.port_open)
        } catch {
            $hs.port_open = $false
            Write-Output ('handshake port probe failed: ' + $_.Exception.Message)
        }
    }
}
Save 'handshake.json' $hs

# ------------------------------------------------------------ 6. process tree
Sec 'PROCESSES'
$procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match '^(SpectrumAgent.*\.exe|app\.exe|msedgewebview2.*\.exe)$' -or
        ($_.CommandLine -and $_.CommandLine -match 'SpectrumAgent')
    } |
    Select-Object ProcessId, ParentProcessId, Name, CreationDate,
                  @{n='cmd';e={$_.CommandLine}}
Write-Output ('matched processes: {0}' -f @($procs).Count)
$procs | Format-Table -AutoSize | Out-String -Width 400 | Write-Output
Save 'processes.json' @($procs)

# ------------------------------------------------------------- 7. LongPaths
Sec 'LONGPATHS'
$lp = $null
try {
    $lp = (Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
} catch {
    Write-Output ('LongPaths read failed: ' + $_.Exception.Message)
}
Write-Output ('LongPathsEnabled={0}' -f $lp)
Save 'longpaths.json' ([pscustomobject]@{ LongPathsEnabled = $lp })

# -------------------------------------------------------- 8. WebView2 runtime
Sec 'WEBVIEW2 RUNTIME'
$wv2 = [pscustomobject]@{
    hklm_wow_pv = $null
    hklm_pv     = $null
    hkcu_pv     = $null
    app_dirs    = @()
    evergreen_dll_version = $null
}
try {
    $wv2.hklm_wow_pv = (Get-ItemProperty -LiteralPath ('HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + $WV2_APPID) -Name pv -ErrorAction Stop).pv
} catch { Write-Output ('wv2 hklm-wow read failed: ' + $_.Exception.Message) }
try {
    $wv2.hklm_pv = (Get-ItemProperty -LiteralPath ('HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\' + $WV2_APPID) -Name pv -ErrorAction Stop).pv
} catch { Write-Output ('wv2 hklm read failed: ' + $_.Exception.Message) }
try {
    $wv2.hkcu_pv = (Get-ItemProperty -LiteralPath ('HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\' + $WV2_APPID) -Name pv -ErrorAction Stop).pv
} catch { Write-Output ('wv2 hkcu read failed: ' + $_.Exception.Message) }
foreach ($base in @("${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application", "$env:ProgramFiles\Microsoft\EdgeWebView\Application")) {
    if (Test-Path -LiteralPath $base) {
        $wv2.app_dirs += Get-ChildItem -LiteralPath $base -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
    }
}
$dll = "${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application"
if (Test-Path -LiteralPath $dll) {
    $exe = Get-ChildItem -LiteralPath $dll -Recurse -Filter 'msedgewebview2.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($exe) {
        try { $wv2.evergreen_dll_version = (Get-Item -LiteralPath $exe.FullName).VersionInfo.ProductVersion } catch { }
    }
}
Write-Output ('wv2 pv: HKLM-WOW={0} HKLM={1} HKCU={2} dirs={3} exe={4}' -f $wv2.hklm_wow_pv, $wv2.hklm_pv, $wv2.hkcu_pv, ($wv2.app_dirs -join ','), $wv2.evergreen_dll_version)
Save 'webview2.json' $wv2

# ------------------------------------------------- 9. network adapter state
Sec 'NETWORK ADAPTERS'
$nics = Get-NetAdapter -ErrorAction SilentlyContinue |
    Select-Object Name, InterfaceDescription, Status, LinkSpeed
$nics | Format-Table -AutoSize | Out-String -Width 300 | Write-Output
Save 'network.json' @($nics)

# ------------------------------------------------------------ 10. stop
Sec 'DONE'
Write-Output ('EVIDENCE_DIR=' + $out)
Write-Output ('PHASE=' + $Phase)
try { Stop-Transcript | Out-Null } catch { }
