<#
  fetch-vm-evidence.ps1
  Host-side counterpart of collect-vm-evidence.ps1.

  WHY THIS EXISTS: Copy-VMFile is host->guest only. There is no supported
  reverse channel (no Copy-VMFile -FileSource Guest, no shared folder in a
  pristine checkpoint, no WinRM configured). The only reliable way to get
  evidence OUT of the guest is to shut it down and mount its VHD read-only.

  WHAT IT DOES:
    1. refuses to run unless the VM is Off
    2. mounts the VM's CURRENT disk read-only
    3. locates \vm-evidence on the mounted volume
    4. copies every evidence folder into <DestRoot>\run-<UTC stamp>\
    5. dismounts, prints a manifest with SHA256 of every copied file

  IT DOES NOT: start/stop/restore/checkpoint the VM, delete checkpoints, or
  judge any result. Run it AFTER the guest is shut down and BEFORE deletecp
  (deleting a checkpoint merges the differencing disk; mounting during a
  merge fails or yields dirty reads).

  USAGE (elevated PowerShell):
    .\fetch-vm-evidence.ps1
    .\fetch-vm-evidence.ps1 -VmName Win11 -DestRoot E:\AI_Agent\artifacts\step4\vm
#>

param(
    [string]$VmName   = 'Win11',
    [string]$DestRoot = 'E:\AI_Agent\artifacts\step4\vm',
    [string]$GuestDir = 'vm-evidence'
)

$ErrorActionPreference = 'Stop'
Import-Module Hyper-V -ErrorAction Stop

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$dest  = Join-Path $DestRoot ("run-" + $stamp)
New-Item -ItemType Directory -Path $dest -Force | Out-Null

$transcript = Join-Path $dest 'fetch-transcript.txt'
Start-Transcript -Path $transcript -Force | Out-Null

try {
    # ---------------------------------------------------------------- guard
    $vm = Get-VM -VMName $VmName
    Write-Output ("VM: {0}  State: {1}" -f $vm.Name, $vm.State)
    if ($vm.State -ne 'Off') {
        throw ("VM state is '{0}'. Shut the guest down from inside (Stop-Computer, NOT -Force) so the filesystem flushes, then re-run." -f $vm.State)
    }

    # ------------------------------------------------------------ disk path
    $drives = @(Get-VMHardDiskDrive -VMName $VmName)
    if ($drives.Count -eq 0) { throw 'No virtual disk attached to the VM.' }
    if ($drives.Count -gt 1) {
        Write-Output 'WARNING: more than one disk attached; using the first.'
        $drives | ForEach-Object { Write-Output ('  - ' + $_.Path) }
    }
    $vhd = $drives[0].Path
    if (-not (Test-Path -LiteralPath $vhd)) { throw ("Disk not found: {0}" -f $vhd) }
    $fi = Get-Item -LiteralPath $vhd
    Write-Output ("Disk: {0}  {1:N2} GB  mtime={2:o}" -f $vhd, ($fi.Length/1GB), $fi.LastWriteTime)

    # ---------------------------------------------------------------- mount
    Write-Output 'Mounting read-only...'
    Mount-VHD -Path $vhd -ReadOnly

    try {
        # find the volume that contains \vm-evidence
        $found = $null
        $vols  = Get-Volume | Where-Object { $_.DriveLetter }
        foreach ($v in $vols) {
            $probe = Join-Path ($v.DriveLetter + ':\') $GuestDir
            if (Test-Path -LiteralPath $probe) {
                $found = $v
                break
            }
        }

        if (-not $found) {
            Write-Output 'No drive letter carried the evidence folder. Volumes seen:'
            $vols | Select-Object DriveLetter, FileSystemLabel, SizeRemaining | Format-Table -AutoSize | Out-String | Write-Output
            throw ("Could not locate '{0}' on any mounted volume. If the guest never created it, the collector did not run." -f $GuestDir)
        }

        $src = Join-Path ($found.DriveLetter + ':\') $GuestDir
        Write-Output ("Evidence source: {0}" -f $src)
        Write-Output ("Evidence folders: {0}" -f (@(Get-ChildItem -LiteralPath $src -Directory).Count))

        # ------------------------------------------------------------- copy
        $payload = Join-Path $dest 'guest'
        New-Item -ItemType Directory -Path $payload -Force | Out-Null
        Copy-Item -Path (Join-Path $src '*') -Destination $payload -Recurse -Force
        Write-Output ("Copied to: {0}" -f $payload)

        # --------------------------------------------------------- manifest
        $rows = Get-ChildItem -LiteralPath $payload -Recurse -File | ForEach-Object {
            [pscustomobject]@{
                rel     = $_.FullName.Substring($payload.Length).TrimStart('\')
                bytes   = $_.Length
                mtime   = $_.LastWriteTime.ToString('o')
                sha256  = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            }
        }
        $rows | ConvertTo-Json -Depth 4 | Out-File -FilePath (Join-Path $dest 'manifest.json') -Encoding UTF8
        Write-Output ("Manifest: {0} files" -f @($rows).Count)
        $rows | Format-Table rel, bytes, sha256 -AutoSize | Out-String -Width 300 | Write-Output
    }
    finally {
        Write-Output 'Dismounting...'
        Dismount-VHD -Path $vhd -ErrorAction SilentlyContinue
    }

    Write-Output ''
    Write-Output ("FETCH_DIR=" + $dest)
    Write-Output 'NEXT: review manifest.json, then remove the temporary checkpoint (vm-ops.ps1 -Action deletecp -Name <temp>).'
}
finally {
    try { Stop-Transcript | Out-Null } catch { }
}
