param([ValidateSet('Capture','CaptureComplete','UninstallRepro','RecoverRepro','InstallDelivery','ProbeDelivery','UninstallDelivery')][string]$Action)
$ErrorActionPreference='Stop'
$out=$PSScriptRoot
$id=[Security.Principal.WindowsIdentity]::GetCurrent()
if($id.Name -notlike '*\Administrator'){throw ('Wrong host identity: '+$id.Name)}
$task='SpectrumAgent-Acceptance-'+$Action+'-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$script=Join-Path $out 'host_task_worker.ps1'
$start=[DateTime]::Now.AddMinutes(3).ToString('yyyy-MM-ddTHH:mm:ss')
$xml=@"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><RegistrationInfo><Description>One-time SpectrumAgent authorized acceptance $Action</Description></RegistrationInfo><Triggers><TimeTrigger><StartBoundary>$start</StartBoundary><Enabled>true</Enabled></TimeTrigger></Triggers><Principals><Principal id="Author"><UserId>$($id.User.Value)</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals><Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><ExecutionTimeLimit>PT15M</ExecutionTimeLimit></Settings><Actions Context="Author"><Exec><Command>C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe</Command><Arguments>-NoProfile -NonInteractive -WindowStyle Hidden -File &quot;$script&quot; -Action $Action</Arguments><WorkingDirectory>E:\AI_Agent</WorkingDirectory></Exec></Actions></Task>
"@
$path=Join-Path $out ('real-task-'+$Action+'.xml')
if(Test-Path -LiteralPath $path){throw 'Task XML exists'}
[IO.File]::WriteAllText($path,$xml,[Text.Encoding]::Unicode)
$log=Join-Path $out ('real-task-'+$Action+'-scheduler-output.txt')
& C:\Windows\System32\schtasks.exe /Create /TN $task /XML $path /F 2>&1|Out-File -LiteralPath $log -Encoding utf8
if($LASTEXITCODE -ne 0){throw 'Task registration failed'}
& C:\Windows\System32\schtasks.exe /Run /TN $task 2>&1|Out-File -LiteralPath $log -Append -Encoding utf8
if($LASTEXITCODE -ne 0){throw 'Task start failed'}
$receipt=Join-Path $out ('real-task-'+$Action+'-result.json')
$deadline=[DateTime]::UtcNow.AddMinutes(10)
while(-not(Test-Path -LiteralPath $receipt) -and [DateTime]::UtcNow -lt $deadline){Start-Sleep -Milliseconds 300}
& C:\Windows\System32\schtasks.exe /Query /TN $task /V /FO LIST 2>&1|Out-File -LiteralPath $log -Append -Encoding utf8
& C:\Windows\System32\schtasks.exe /Delete /TN $task /F 2>&1|Out-File -LiteralPath $log -Append -Encoding utf8
[ordered]@{task=$task;action=$Action;identity=$id.Name;sid=$id.User.Value;xml=$path;receipt_exists=Test-Path -LiteralPath $receipt;deleted_exit=$LASTEXITCODE;finished_utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Out-File -LiteralPath (Join-Path $out ('real-task-'+$Action+'-scheduler-receipt.json')) -Encoding utf8
