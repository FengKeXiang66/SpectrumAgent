param([ValidateSet('Close','KillReady','KillStarting')][string]$Mode,[int]$Rounds=10)
$ErrorActionPreference='Stop'
$root='E:\AI_Agent\artifacts\step3\checkpoint-4\release-custom-protocol-20261018\final-canonical-20261019'
$stamp=[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$receipt=Join-Path $root ("repro-explorer-$Mode-$stamp-receipt.json")
$console=Join-Path $root ("repro-explorer-$Mode-$stamp-console.txt")
$outcome=[ordered]@{mode=$Mode;rounds=$Rounds;runner_pid=$PID;console=$console;status='running';error=$null}
$outcome|ConvertTo-Json|Set-Content -LiteralPath $receipt -Encoding utf8
& {
  try { & (Join-Path $root 'repro_lifecycle.ps1') -Mode $Mode -Rounds $Rounds; $outcome.status='passed' }
  catch {
    $_ | Format-List * -Force; $outcome.status='failed';$outcome.error=$_.Exception.Message
    $owned=$global:SpectrumAcceptanceOwnedProcess
    if($owned){
      $still=Get-CimInstance Win32_Process -Filter "ProcessId=$($owned.ProcessId)"
      if($still -and $still.CreationDate -eq $owned.CreationDate){
        $image=[JobProbe]::ImagePath($owned.ProcessId)
        if((Normalize-Executable $image) -ieq 'E:\AI_Agent\src-tauri\target\repro-check\release\spectrum-agent.exe'){
          Write-Output "TEST_HYGIENE_ONLY: stopping owned shell PID $($owned.ProcessId) after failed verdict; not acceptance evidence"
          Stop-Process -Id $owned.ProcessId -Force
        }
      }
    }
  }
} *>&1 | Out-File -LiteralPath $console -Encoding utf8 -Width 10000
$outcome|ConvertTo-Json|Set-Content -LiteralPath $receipt -Encoding utf8
