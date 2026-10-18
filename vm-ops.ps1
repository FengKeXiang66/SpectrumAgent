<#
  vm-ops.ps1 - Day-to-day VM acceptance helpers for Win11Clean
  Run in ELEVATED PowerShell.

  Examples:
    .\vm-ops.ps1 -Action checkpoint -Name pristine      # after clean OS install
    .\vm-ops.ps1 -Action restore    -Name pristine      # before each acceptance round
    .\vm-ops.ps1 -Action send       -SourcePath "E:\AI_Agent\dist\setup.exe"   # copy into VM desktop
    .\vm-ops.ps1 -Action status
    .\vm-ops.ps1 -Action deletecp   -Name someTempCheckpoint
#>
param(
    [Parameter(Mandatory=$true)][ValidateSet("checkpoint","restore","send","status","deletecp")]
    [string]$Action,
    [string]$Name,
    [string]$SourcePath,
    [string]$VmName = "Win11"
)

$ErrorActionPreference = "Stop"
Import-Module Hyper-V -ErrorAction Stop

switch ($Action) {

    "checkpoint" {
        if (-not $Name) { throw "checkpoint requires -Name" }
        Checkpoint-VM -VMName $VmName -SnapshotName $Name
        Write-Host "Checkpoint '$Name' created on '$VmName'."
    }

    "restore" {
        if (-not $Name) { throw "restore requires -Name" }
        Stop-VM -VMName $VmName -Force -ErrorAction SilentlyContinue
        Restore-VMCheckpoint -VMName $VmName -Name $Name -Confirm:$false
        Start-VM -VMName $VmName
        Write-Host "Restored '$Name' and started. Wait ~30s for the desktop."
    }

    "send" {
        if (-not $SourcePath) { throw "send requires -SourcePath" }
        if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) { throw "file not found: $SourcePath" }
        # Localized-safe match: EN "Guest Service Interface" or zh-CN guest-service name.
        # Use \uXXXX escapes so this file stays pure ASCII (PS 5.1 reads .ps1 as GBK).
        $gs = Get-VMIntegrationService -VMName $VmName |
              Where-Object { $_.Name -match '^(Guest Service Interface|\u6765\u5bbe\u670d\u52a1\u63a5\u53e3)$' }
        if (-not $gs) { throw "Guest Service Interface not found on $VmName" }
        Enable-VMIntegrationService -VMName $VmName -Name $gs.Name
        $dest = "C:\Users\Public\Desktop\" + (Split-Path $SourcePath -Leaf)
        Copy-VMFile -VMName $VmName -SourcePath $SourcePath -DestinationPath $dest -FileSource Host -CreateFullPath -Force
        $h = Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256
        Write-Host "Copied to VM: $dest  (source SHA256: $($h.Hash))"
        Write-Host "Verify in guest: Get-FileHash 'C:\Users\Public\Desktop\$(Split-Path $SourcePath -Leaf)' -Algorithm SHA256"
    }

    "status" {
        $vm = Get-VM -VMName $VmName
        "VM: $($vm.Name)  State: $($vm.State)  Uptime: $($vm.Uptime)"
        "Memory assigned: $([math]::Round($vm.MemoryAssigned/1GB,1)) GB  CPUs: $($vm.ProcessorCount)"
        "--- security / firmware / guest file copy ---"
        Get-VMSecurity -VMName $VmName | Select-Object VMName, TpmEnabled | Format-List
        Get-VMFirmware -VMName $VmName | Select-Object VMName, SecureBoot, SecureBootTemplate | Format-List
        Get-VMIntegrationService -VMName $VmName | Select-Object Name, Enabled, PrimaryStatusDescription | Format-Table -AutoSize
        "--- checkpoints ---"
        Get-VMCheckpoint -VMName $VmName | Select-Object Name, CreationTime | Format-Table -AutoSize
        "--- VHDX sizes ---"
        Get-VMHardDiskDrive -VMName $VmName | ForEach-Object {
            $p = $_.Path
            if (Test-Path $p) {
                $f = Get-Item $p
                "{0,-12} {1,8:N1} GB" -f (Split-Path $p -Leaf), ($f.Length/1GB)
            }
        }
    }

    "deletecp" {
        if (-not $Name) { throw "deletecp requires -Name" }
        Remove-VMCheckpoint -VMName $VmName -Name $Name -Confirm:$false
        Write-Host "Checkpoint '$Name' removed. Keep only 'pristine' between rounds."
    }
}
