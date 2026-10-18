<#
  deploy-win11-vhdx.ps1 - Recreate the VM disk and deploy Win11 Pro onto it.
  Why recreate: earlier failed runs left the VHDX in an inconsistent state
  (Get-Disk says GPT, New-Partition says not initialized, then RAW on remount).
  A fresh VHDX removes all doubt.

  Run in ELEVATED PowerShell. VM is stopped automatically.
  Flow: stop VM -> disable auto checkpoints -> delete+recreate disk.vhdx
        -> mount ISO+VHDX -> GPT -> ESP/MSR/Windows -> dism apply (index 4)
        -> bcdboot UEFI -> detach -> first boot = disk (Secure Boot Off) -> start
  ASCII-only on purpose (PS 5.1 reads .ps1 as GBK when no BOM).
#>
param(
    [string]$VmName       = "Win11",
    [string]$IsoPath      = "E:\ISO\Windows11_Client_x64_zh-cn_26300_9457.iso",
    [int]   $ImageIndex   = 4,
    [long]  $DiskSizeBytes = 80GB
)
$ErrorActionPreference = "Stop"
Import-Module Hyper-V -ErrorAction Stop

# --- 0. preconditions ---
if (-not (Test-Path -LiteralPath $IsoPath -PathType Leaf)) { throw "ISO not found: $IsoPath" }
foreach ($l in @("T:\","S:\")) {
    if (Test-Path $l) { throw "Drive letter $l already in use - free it first" }
}

# --- 1. stop VM (must be Off) + kill automatic checkpoints ---
$vm = Get-VM -Name $VmName
if ($vm.State -ne "Off") {
    Stop-VM -VMName $VmName -Force
    $t0 = Get-Date
    while ((Get-VM -Name $VmName).State -ne "Off" -and ((Get-Date) - $t0).TotalSeconds -lt 60) { Start-Sleep -Seconds 2 }
}
if ((Get-VM -Name $VmName).State -ne "Off") { throw "VM did not stop within 60s" }
Set-VM -VMName $VmName -AutomaticCheckpointsEnabled $false
"VM is Off; automatic checkpoints disabled."

# --- 2. recreate the VM's VHDX file (fresh, no stale partition metadata) ---
$vhd = (Get-VMHardDiskDrive -VMName $VmName | Select-Object -First 1).Path
if (-not $vhd) { throw "no hard disk attached to $VmName" }
"Recreating disk: $vhd"
Remove-Item -LiteralPath $vhd -Force
New-VHD -Path $vhd -Dynamic -SizeBytes $DiskSizeBytes | Out-Null
"Fresh VHDX created ($([math]::Round($DiskSizeBytes/1GB)) GB dynamic)."

# --- 3. mount ISO read-only + VHDX, GPT partitions ---
$img = Mount-DiskImage -ImagePath $IsoPath -PassThru
$isoLetter = ($img | Get-Volume).DriveLetter
"ISO mounted at ${isoLetter}:\"
$vhdObj = Mount-VHD -Path $vhd -Passthru

try {
    $vhdObj | Initialize-Disk -PartitionStyle GPT | Out-Null
    $d = $vhdObj | Get-Disk
    if ($d.PartitionStyle -ne "GPT") { throw "Initialize-Disk did not stick (PartitionStyle=$($d.PartitionStyle))" }
    $dnum = $d.Number
    "Disk $dnum initialized as GPT."

    $esp = New-Partition -DiskNumber $dnum -Size 260MB -GptType "{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}"
    Format-Volume -Partition $esp -FileSystem FAT32 -Confirm:$false | Out-Null
    New-Partition -DiskNumber $dnum -Size 16MB -GptType "{e3c9e316-0b5c-4db8-817d-f92df00215ae}" | Out-Null
    $win = New-Partition -DiskNumber $dnum -UseMaximumSize -GptType "{ebd0a0a2-b9e5-4433-87c0-68b6b72699c7}"
    Format-Volume -Partition $win -FileSystem NTFS -Confirm:$false | Out-Null
    Add-PartitionAccessPath -DiskNumber $dnum -PartitionNumber $esp.PartitionNumber -AccessPath "T:\"
    Add-PartitionAccessPath -DiskNumber $dnum -PartitionNumber $win.PartitionNumber -AccessPath "S:\"
    "Partitions ready: ESP=FAT32 260MB, MSR=16MB, Windows=NTFS (T:=ESP, S:=Windows)"

    # --- 4. apply image (index 4 = Pro) ---
    "Applying install.wim index $ImageIndex ... expect 5-10 minutes, do not close."
    dism /Apply-Image /ImageFile:"${isoLetter}:\sources\install.wim" /Index:$ImageIndex /ApplyDir:S:\
    if ($LASTEXITCODE -ne 0) { throw "dism /Apply-Image failed (exit $LASTEXITCODE)" }
    "Image applied."

    # --- 5. UEFI boot files ---
    bcdboot S:\Windows /s T: /f UEFI
    if ($LASTEXITCODE -ne 0) { throw "bcdboot failed (exit $LASTEXITCODE)" }
    "Boot files written to ESP."
}
finally {
    Dismount-VHD -Path $vhd -ErrorAction SilentlyContinue | Out-Null
    Dismount-DiskImage -ImagePath $IsoPath -ErrorAction SilentlyContinue | Out-Null
    "VHDX + ISO detached."
}

# --- 6. boot from hard disk first; Secure Boot Off for first boot ---
Set-VMFirmware -VMName $VmName -FirstBootDevice (Get-VMHardDiskDrive -VMName $VmName | Select-Object -First 1)
Set-VMFirmware -VMName $VmName -EnableSecureBoot Off
Start-VM -VMName $VmName
""
"Done. Connect with:  vmconnect.exe localhost $VmName"
"OOBE: no product key -> Pro -> if network step forces online:"
"  Shift+F10 -> oobe\bypassnro (reboot) -> 'I don't have Internet' -> local account 'test'"
"  fallback: Shift+F10 -> start ms-cxh:localonly"
""
"After OOBE + desktop is up, turn Secure Boot back On (VM Off) then checkpoint:"
"  Stop-VM -VMName $VmName -Force; Set-VMFirmware -VMName $VmName -EnableSecureBoot On"
"  .\vm-ops.ps1 -Action checkpoint -Name pristine -VmName $VmName"
