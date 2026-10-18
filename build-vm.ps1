<#
  build-vm.ps1 - Create the Win11 clean VM for Phase-1 acceptance (TASK-01)
  Run in ELEVATED PowerShell. All VM storage goes to E: (C: has <16GB free).
  Default ISO: E:\ISO\Windows11_Client_x64_zh-cn_26300_9457.iso (8.49GB, verified)

  Steps after running this script:
    1. Open vmconnect.exe localhost Win11Clean -> install Windows (Pro edition)
    2. Complete OOBE; available offline-account options depend on the ISO build
    3. Then run:  .\vm-ops.ps1 -Action checkpoint -Name pristine
#>
param(
    [string]$IsoPath = "E:\ISO\Windows11_Client_x64_zh-cn_26300_9457.iso",
    [string]$VmName  = "Win11Clean",
    [string]$VmRoot  = "E:\HyperV\Win11Clean"
)

$ErrorActionPreference = "Stop"
Import-Module Hyper-V -ErrorAction Stop

if (-not (Test-Path -LiteralPath $IsoPath -PathType Leaf)) { throw "ISO not found: $IsoPath" }
$VmRoot = [System.IO.Path]::GetFullPath($VmRoot)

# --- Idempotent: create only if missing; if it exists, just (re)apply the config below ---
$existing = Get-VM -Name $VmName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "VM '$VmName' already exists -> skipping creation, applying remaining config."
} else {
    if (-not $VmRoot.StartsWith('E:\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "VM storage must stay on E: $VmRoot"
    }
    if ((Test-Path -LiteralPath $VmRoot) -and @(Get-ChildItem -LiteralPath $VmRoot -Force).Count -gt 0) {
        throw "VM directory is not empty; refusing to reuse it: $VmRoot"
    }
    New-Item -ItemType Directory -Path $VmRoot -Force | Out-Null

    # --- Network switch: prefer "Default Switch" (NAT), fall back to Internal VMNet ---
    $switch = Get-VMSwitch -Name "Default Switch" -ErrorAction SilentlyContinue
    if (-not $switch) {
        $switch = Get-VMSwitch -Name "VMNet" -ErrorAction SilentlyContinue
        if (-not $switch) {
            Write-Host "Default Switch missing -> creating Internal switch 'VMNet'"
            $switch = New-VMSwitch -Name "VMNet" -SwitchType Internal
        }
    }
    Write-Host "Using switch: $($switch.Name)"

    # --- VM (Gen2, dynamic memory 4-10GB, 4 vCPU, 80GB VHDX on E:) ---
    New-VM -Name $VmName -Generation 2 `
           -MemoryStartupBytes 6GB `
           -NewVHDPath "$VmRoot\disk.vhdx" -NewVHDSizeBytes 80GB `
           -SwitchName $switch.Name -Path $VmRoot
}

Set-VMMemory   -VMName $VmName -DynamicMemoryEnabled $true -MinimumBytes 4GB -MaximumBytes 10GB
Set-VMProcessor -VMName $VmName -Count 4
Set-VMKeyProtector -VMName $VmName -NewLocalKeyProtector
Enable-VMTPM   -VMName $VmName
Set-VMFirmware -VMName $VmName -EnableSecureBoot On
# NOTE: localized-safe match via \uXXXX escapes so this file stays pure ASCII
# (PS 5.1 reads .ps1 as GBK without BOM - Chinese literals would break matching).
$gs = Get-VMIntegrationService -VMName $VmName |
      Where-Object { $_.Name -match '^(Guest Service Interface|\u6765\u5bbe\u670d\u52a1\u63a5\u53e3)$' }
if ($gs) {
    Enable-VMIntegrationService -VMName $VmName -Name $gs.Name
    Write-Host "Guest Service Interface enabled ($($gs.Name))."
} else {
    Write-Warning "Guest Service Interface not found; Copy-VMFile delivery will need a fallback."
}
Set-VM         -VMName $VmName -AutomaticCheckpointsEnabled $false   # manual checkpoints only
if (-not (Get-VMDvdDrive -VMName $VmName | Where-Object { $_.Path -eq $IsoPath })) {
    $dvd = Add-VMDvdDrive -VMName $VmName -Path $IsoPath -Passthru
    Set-VMFirmware -VMName $VmName -FirstBootDevice $dvd
    Write-Host "ISO attached and set as first boot device."
} else {
    Write-Host "ISO already attached."
}

Write-Host ""
Write-Host "VM '$VmName' created at $VmRoot"
Write-Host "Config dir contents:"
Get-ChildItem $VmRoot | Format-Table Name, Length -AutoSize

Start-VM -VMName $VmName
Get-VM -Name $VmName | Select-Object Name, State, Generation
Get-VMSecurity -VMName $VmName | Select-Object VMName, TpmEnabled
Get-VMFirmware -VMName $VmName | Select-Object VMName, SecureBoot, SecureBootTemplate
Get-VMIntegrationService -VMName $VmName | Select-Object Name, Enabled, PrimaryStatusDescription
Write-Host "VM started. Open 'vmconnect.exe localhost $VmName' to install Windows 11 PRO."
