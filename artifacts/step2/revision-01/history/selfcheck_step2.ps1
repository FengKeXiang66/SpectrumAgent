param([int]$SendCtrlCTo = 0)

$ErrorActionPreference = 'Stop'
$stepRoot = $PSScriptRoot
Add-Type -Path (Join-Path $stepRoot 'NativeConsole.cs')
if ($SendCtrlCTo -gt 0) {
    [SpectrumTestConsole]::SendCtrlC([uint32]$SendCtrlCTo)
    exit 0
}

$exe = Join-Path $stepRoot 'dist\app\app.exe'
$internal = Join-Path $stepRoot 'dist\app\_internal'
$dataRoot = Join-Path $env:LOCALAPPDATA 'SpectrumAgent'
$hsPath = Join-Path $dataRoot 'run\handshake.json'
$engine = $null
$identity = $null
$currentCheck = 'preflight'
$nativeProcessIds = [System.Collections.Generic.List[int]]::new()
$savedPath = $env:PATH
$testStarted = [DateTime]::UtcNow
$transcript = Join-Path $stepRoot 'selfcheck-output.txt'
$results = [ordered]@{}
$timings = [ordered]@{}
$script:failed = $false
Start-Transcript -LiteralPath $transcript -Force | Out-Null

function Read-Handshake {
    if (Test-Path -LiteralPath $hsPath) {
        return Get-Content -LiteralPath $hsPath -Raw | ConvertFrom-Json -DateKind String
    }
    return $null
}

function Save-RedactedHandshake {
    param($Handshake, [string]$FileName)
    $copy = $Handshake | ConvertTo-Json | ConvertFrom-Json -DateKind String
    $copy.token = '<redacted>'
    $json = $copy | ConvertTo-Json -Depth 8
    $json | Set-Content -LiteralPath (Join-Path $stepRoot $FileName) -Encoding utf8NoBOM
    Write-Output $json
}

function Start-Engine {
    param([string]$Name)
    $clock = [Diagnostics.Stopwatch]::StartNew()
    Write-Output ('> CreateProcessW("' + $exe + '") [CREATE_NEW_CONSOLE, SW_HIDE; no Python/command shell]')
    $script:engine = Get-Process -Id ([SpectrumTestConsole]::Start($exe, $stepRoot))
    $null = $script:engine.Handle # retain a handle so ExitCode remains available
    $script:nativeProcessIds.Add($script:engine.Id)
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $deadline) {
        $script:engine.Refresh()
        if ($script:engine.HasExited) { throw "Engine exited before handshake: $($script:engine.ExitCode)" }
        $candidate = Read-Handshake
        if ($candidate -and $candidate.pid -eq $script:engine.Id) {
            $script:identity = $candidate
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$($candidate.port)/health" -NoProxy -TimeoutSec 2
            $health = $response.Content | ConvertFrom-Json
            if ($response.StatusCode -eq 200 -and $health.boot_id -eq $candidate.boot_id -and $health.pid -eq $candidate.pid) {
                $clock.Stop()
                $script:timings[$Name] = [Math]::Round($clock.Elapsed.TotalMilliseconds, 3)
                Write-Output "spawn_pid=$($script:engine.Id) handshake_pid=$($candidate.pid) health_pid=$($health.pid)"
                Write-Output "${Name}_process_start_to_health_200_ms=$($script:timings[$Name])"
                return
            }
        }
        Start-Sleep -Milliseconds 20
    }
    throw 'Engine did not become healthy within 30 seconds.'
}

function Invoke-CurlCheck {
    param([string]$Path, [int]$ExpectedCode, [string]$Name, [switch]$Authenticated)
    $url = "http://127.0.0.1:$($script:identity.port)$Path"
    $body = Join-Path $stepRoot "$Name.json"
    $argsForCurl = @('--silent', '--show-error', '--noproxy', '*', '--max-time', '30', '-o', $body, '-w', '%{http_code}')
    if ($Authenticated) {
        $argsForCurl += @('-H', "Authorization: Bearer $($script:identity.token)")
        Write-Output ('> curl.exe --noproxy "*" -H "Authorization: Bearer $($identity.token)" ' + $url)
    } else { Write-Output ('> curl.exe --noproxy "*" ' + $url) }
    $code = & curl.exe @argsForCurl $url
    if ($LASTEXITCODE -ne 0) { throw "curl failed with exit code $LASTEXITCODE" }
    $raw = Get-Content -LiteralPath $body -Raw
    Write-Output "HTTP $code"
    Write-Output $raw
    if ([int]$code -ne $ExpectedCode) { throw "Expected HTTP $ExpectedCode, got $code" }
    return $null
}

function Run-Diagnostic {
    param([string]$Argument, [string]$Name)
    $start = [Diagnostics.ProcessStartInfo]::new($exe)
    $start.ArgumentList.Add($Argument)
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = [Text.Encoding]::UTF8
    $start.StandardErrorEncoding = [Text.Encoding]::UTF8
    $start.WorkingDirectory = $stepRoot
    Write-Output ('> & "' + $exe + '" ' + $Argument)
    $process = [Diagnostics.Process]::Start($start)
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(30000)) {
        $process.Kill($true)
        throw "Diagnostic $Name timed out."
    }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    [IO.File]::WriteAllText((Join-Path $stepRoot "$Name.stdout.txt"), $stdout)
    [IO.File]::WriteAllText((Join-Path $stepRoot "$Name.stderr.txt"), $stderr)
    Write-Output "exit_code=$($process.ExitCode)"
    Write-Output $stdout
    if ($process.ExitCode -ne 0) { Write-Output $stderr; throw "Diagnostic $Name failed." }
    $process.Dispose()
}

function Assert-NoEngine {
    param([int]$EnginePid, [int]$Port)
    if (Get-Process -Id $EnginePid -ErrorAction SilentlyContinue) { throw "Engine PID $EnginePid remains." }
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw "Port $Port remains listening." }
    Write-Output "process_absent=True pid=$EnginePid listener_absent=True port=$Port"
}

function Stop-Normally {
    $closing = $script:identity
    Write-Output "> GenerateConsoleCtrlEvent(CTRL_C_EVENT) to PID $($closing.pid) [separate helper attaches to engine console]"
    $powerShellExe = (Get-Process -Id $PID).Path
    $helper = Start-Process -FilePath $powerShellExe -ArgumentList @('-NoProfile', '-File', $PSCommandPath, '-SendCtrlCTo', [string]$closing.pid) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $stepRoot 'ctrlc.stdout.txt') -RedirectStandardError (Join-Path $stepRoot 'ctrlc.stderr.txt')
    if (-not $helper.WaitForExit(15000)) { throw 'Ctrl+C helper timed out.' }
    if ($helper.ExitCode -ne 0) {
        Get-Content -LiteralPath (Join-Path $stepRoot 'ctrlc.stderr.txt') -Raw | Write-Output
        throw "Ctrl+C helper failed: $($helper.ExitCode)"
    }
    if (-not $script:engine.WaitForExit(10000)) { throw 'Engine ignored normal Ctrl+C shutdown.' }
    Write-Output "engine_exit_code=$($script:engine.ExitCode)"
    Assert-NoEngine $closing.pid $closing.port
    if (Test-Path -LiteralPath $hsPath) { throw 'Handshake remains after normal exit, before test hygiene.' }
    Write-Output 'handshake_exists=False (checked before any test hygiene)'
    $script:engine = $null
}

try {
    if (-not (Test-Path -LiteralPath $exe)) { throw "Missing frozen engine: $exe" }
    foreach ($name in @('GDAL_DATA', 'PROJ_DATA', 'PROJ_LIB')) {
        $value = [Environment]::GetEnvironmentVariable($name, 'Process')
        Write-Output "$name=$value"
        if ($null -ne $value) { throw "$name is already set; this check requires the observed unset environment." }
    }
    $old = Read-Handshake
    if ($old -and (Get-Process -Id $old.pid -ErrorAction SilentlyContinue)) { throw 'Existing handshake PID is alive; refusing to overwrite a live engine.' }
    if ($old) {
        Write-Output 'PREFLIGHT TEST HYGIENE ONLY: archive and remove a pre-existing dead-process handshake before the first launch.'
        Save-RedactedHandshake $old 'handshake-before-first-launch.json'
        Remove-Item -LiteralPath $hsPath
        if (Test-Path -LiteralPath $hsPath) { throw 'Pre-existing handshake could not be removed.' }
    }
    $others = @(Get-CimInstance Win32_Process -Filter "Name = 'app.exe'")
    if ($others.Count -gt 0) { throw 'An app.exe already exists; refusing to mix process evidence.' }
    # Child processes see only Windows tooling; no PATH Python/GDAL or project cwd.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    Write-Output "child_PATH=$env:PATH"

    $currentCheck = '1'
    Write-Output '=== 1. Direct frozen engine launch / process identity ==='
    Start-Engine 'first_launch'
    Write-Output '> tasklist.exe /FI "IMAGENAME eq app.exe"'
    tasklist.exe /FI 'IMAGENAME eq app.exe'
    Write-Output '> Get-CimInstance Win32_Process -Filter "Name = ''app.exe''"'
    $rows = @(Get-CimInstance Win32_Process -Filter "Name = 'app.exe'")
    $rows | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | Format-List | Out-String | Write-Output
    Write-Output "app_process_count=$($rows.Count)"
    if ($rows.Count -ne 1 -or $rows[0].ProcessId -ne $identity.pid) { throw 'Unexpected frozen engine process model.' }
    $actualCreation = $engine.StartTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    if ($actualCreation -ne $identity.process_created_at) { throw 'Windows process creation time differs from handshake.' }
    $results['1'] = 'PASS'

    $currentCheck = '2'
    Write-Output '=== 2. Four real curl requests ==='
    Invoke-CurlCheck '/health' 200 'health'
    $health = Get-Content -LiteralPath (Join-Path $stepRoot 'health.json') -Raw | ConvertFrom-Json
    if ($health.boot_id -ne $identity.boot_id -or $health.pid -ne $identity.pid) { throw 'Health identity mismatch.' }
    Invoke-CurlCheck '/smoke' 401 'unauthorized'
    Invoke-CurlCheck '/smoke' 200 'smoke' -Authenticated
    Invoke-CurlCheck '/smoke?blocks=8' 200 'smoke-blocks' -Authenticated
    foreach ($name in @('smoke', 'smoke-blocks')) {
        $metrics = Get-Content -LiteralPath (Join-Path $stepRoot "$name.json") -Raw | ConvertFrom-Json
        foreach ($field in @('nan_ratio', 'reflectance_range', 'bands', 'shape', 'elapsed_ms')) {
            if ($field -notin $metrics.PSObject.Properties.Name) { throw "Missing $field in $name" }
        }
        if ($metrics.nan_ratio -ne 0 -or $metrics.bands -ne 8 -or ($metrics.shape -join ',') -ne '8,8,8') { throw "Invalid $name metrics." }
    }
    $results['2'] = 'PASS'

    $currentCheck = '3'
    Write-Output '=== 3. Complete handshake (token redacted only) ==='
    if ($identity.token -cnotmatch '^[0-9a-f]{32}$') { throw 'Handshake token is not 32 hex characters.' }
    Save-RedactedHandshake $identity 'handshake.json'
    $results['3'] = 'PASS'

    $currentCheck = '4'
    Write-Output '=== 4. JSONL logs ==='
    $logFiles = @(Get-ChildItem -LiteralPath (Join-Path $dataRoot 'logs') -Filter 'engine-*.jsonl')
    $lineCount = 0
    $currentLines = @()
    foreach ($file in $logFiles) {
        foreach ($line in (Get-Content -LiteralPath $file.FullName)) {
            $parsed = $line | ConvertFrom-Json
            $lineCount += 1
            if ($line.Contains($identity.token)) { throw 'Token leaked into log.' }
            if ($parsed.boot_id -eq $identity.boot_id) { $currentLines += $line }
        }
    }
    if ($currentLines.Count -lt 3) { throw 'Fewer than 3 log lines with current boot_id.' }
    Write-Output "valid_json_lines=$lineCount current_boot_lines=$($currentLines.Count) token_occurrences=0"
    $currentLines | Select-Object -First 3 | Tee-Object -FilePath (Join-Path $stepRoot 'log-samples.jsonl') | Write-Output
    $results['4'] = 'PASS'

    $currentCheck = '5'
    Write-Output '=== 5. Frozen GeoTIFF generation / readback (no external interpreter) ==='
    Run-Diagnostic '--selfcheck-geotiff' 'geotiff'
    $geo = Get-Content -LiteralPath (Join-Path $stepRoot 'geotiff.stdout.txt') -Raw | ConvertFrom-Json
    if (-not $geo.frozen -or $geo.crs -ne 'EPSG:32650' -or $geo.count -ne 3 -or ($geo.shape -join ',') -ne '10,12') { throw 'GeoTIFF result mismatch.' }
    if (($geo.transform -join ',') -ne '30,0,500000,0,-30,4000000') { throw 'GeoTIFF transform mismatch.' }
    if (-not $geo.sample_removed -or -not $geo.pixel_values_equal) { throw 'GeoTIFF sample cleanup / pixel mismatch.' }
    if ($null -ne $geo.GDAL_DATA -or $null -ne $geo.PROJ_DATA) { throw 'GeoTIFF diagnostic set GDAL/PROJ environment variables.' }
    foreach ($module in @($geo.rasterio_module, $geo.numpy_module)) {
        if (-not $module.StartsWith($internal, [StringComparison]::OrdinalIgnoreCase)) { throw "Module outside bundle: $module" }
    }
    $results['5'] = 'PASS'

    $currentCheck = 'multiprocessing'
    Write-Output '=== Additional: freeze_support / one temporary spawn worker (no pool) ==='
    Run-Diagnostic '--selfcheck-worker' 'multiprocessing'
    $worker = Get-Content -LiteralPath (Join-Path $stepRoot 'multiprocessing.stdout.txt') -Raw | ConvertFrom-Json
    if (-not $worker.frozen -or -not $worker.handshake_unchanged -or $worker.worker_exitcode -ne 0) { throw 'Frozen worker check failed.' }
    $results['multiprocessing'] = 'PASS'

    $currentCheck = '7'
    Write-Output '=== 7. Size / first-launch health latency ==='
    $files = @(Get-ChildItem -LiteralPath $internal -Recurse -File)
    $internalBytes = ($files | Measure-Object -Property Length -Sum).Sum
    $dlls = @(Get-ChildItem -LiteralPath (Join-Path $internal 'rasterio.libs') -Filter '*.dll' -File)
    $pyds = @(Get-ChildItem -LiteralPath (Join-Path $internal 'rasterio') -Filter '*.pyd' -File)
    Write-Output "internal_files=$($files.Count) internal_total_bytes=$internalBytes exe_bytes=$((Get-Item -LiteralPath $exe).Length)"
    Write-Output "rasterio_libs_dll_count=$($dlls.Count) rasterio_pyd_count=$($pyds.Count)"
    Write-Output "first_launch_process_start_to_health_200_ms=$($timings['first_launch'])"
    Write-Output 'Timing scope: first launch of this build in this selfcheck; no OS cache flush or clean-machine cold boot was performed.'
    if ($dlls.Count -ne 36 -or $pyds.Count -ne 15) { throw 'Unexpected rasterio binary inventory.' }
    $dlls | Select-Object Name,Length | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stepRoot 'rasterio-dll-inventory.json') -Encoding utf8NoBOM
    $results['7'] = 'PASS'

    $currentCheck = '8a'
    Write-Output '=== 8a. Normal Ctrl+C shutdown ==='
    Stop-Normally
    $results['8a'] = 'PASS'

    $currentCheck = '6'
    Write-Output '=== 6. Required DLL removal / native readable failure ==='
    $dll = Join-Path $internal 'python312.dll'
    $backup = Join-Path $stepRoot 'python312.dll.test-backup'
    $resolvedRoot = [IO.Path]::GetFullPath($stepRoot) + [IO.Path]::DirectorySeparatorChar
    foreach ($target in @($dll, $backup)) {
        if (-not ([IO.Path]::GetFullPath($target)).StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'DLL test target escaped step2 directory.' }
    }
    $dllHash = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash
    if (Test-Path -LiteralPath $backup) { throw 'DLL backup already exists; refusing overwrite.' }
    Copy-Item -LiteralPath $dll -Destination $backup
    Remove-Item -LiteralPath $dll
    Write-Output "> Removed $dll (backup retained outside _internal)"
    try {
        $start = [Diagnostics.ProcessStartInfo]::new($exe)
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        $broken = [Diagnostics.Process]::Start($start)
        $brokenOut = $broken.StandardOutput.ReadToEndAsync()
        $brokenErr = $broken.StandardError.ReadToEndAsync()
        if (-not $broken.WaitForExit(10000)) { $broken.Kill($true); throw 'Missing DLL failure did not exit within 10 seconds.' }
        $message = $brokenOut.GetAwaiter().GetResult() + $brokenErr.GetAwaiter().GetResult()
        Write-Output "exit_code=$($broken.ExitCode)"
        Write-Output $message
        $message | Set-Content -LiteralPath (Join-Path $stepRoot 'missing-dll-output.txt') -Encoding utf8NoBOM
        if ($broken.ExitCode -eq 0 -or $message -notmatch 'python312.dll' -or $message -notmatch 'Failed to load Python DLL') { throw 'Missing DLL failure was not explicit.' }
        if ($message -match 'Traceback \(most recent call last\)') { throw 'Missing DLL emitted only a Python traceback.' }
        if (Test-Path -LiteralPath $hsPath) { throw 'Broken bundle unexpectedly published handshake.' }
    } finally {
        Move-Item -LiteralPath $backup -Destination $dll
        if ((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -ne $dllHash) { throw 'Restored DLL hash differs.' }
        Write-Output 'Required DLL restored; SHA256 matches original.'
    }
    $results['6'] = 'PASS'

    $currentCheck = '8b'
    Write-Output '=== 8b. taskkill /F / stale-handshake overwrite without pre-clean ==='
    Start-Engine 'kill_test_launch'
    $killed = $identity
    Write-Output "> taskkill.exe /F /PID $($killed.pid)"
    taskkill.exe /F /PID $killed.pid
    if ($LASTEXITCODE -ne 0) { throw 'taskkill /F failed.' }
    if (-not $engine.WaitForExit(10000)) { throw 'Killed engine did not exit.' }
    Assert-NoEngine $killed.pid $killed.port
    Write-Output "> tasklist.exe /FI `"PID eq $($killed.pid)`""
    tasklist.exe /FI "PID eq $($killed.pid)"
    if (-not (Test-Path -LiteralPath $hsPath)) { throw 'Expected handshake residue after hard kill was not observed.' }
    $residue = Read-Handshake
    if ($residue.boot_id -ne $killed.boot_id) { throw 'Unexpected handshake generation after kill.' }
    Write-Output 'handshake_exists_after_taskkill=True; residue before any hygiene:'
    Save-RedactedHandshake $residue 'handshake-after-kill.json'
    $residueBytes = [IO.File]::ReadAllBytes($hsPath)
    Write-Output 'Restarting directly; no handshake deletion or rewrite by harness.'
    Start-Engine 'stale_restart'
    if ($identity.boot_id -eq $killed.boot_id -or $identity.port -eq $killed.port) { throw 'Restart did not change boot_id and port as required.' }
    Write-Output "old_boot_id=$($killed.boot_id) new_boot_id=$($identity.boot_id)"
    Write-Output "old_port=$($killed.port) new_port=$($identity.port)"
    Invoke-CurlCheck '/health' 200 'health-after-restart'
    $results['8b'] = 'PASS'
    Write-Output '=== Final normal exit / test hygiene ==='
    Stop-Normally
    Write-Output 'No hygiene deletion was needed; any fallback cleanup below is test hygiene, never a pass criterion.'
    Write-Output '> tasklist.exe /FI "IMAGENAME eq app.exe"'
    tasklist.exe /FI 'IMAGENAME eq app.exe'
    foreach ($number in @('1','2','3','4','5','6','7','8a','8b','multiprocessing')) {
        Write-Output "CHECK_${number}=$($results[$number])"
    }
} catch {
    $script:failed = $true
    $results[$currentCheck] = 'FAIL'
    Write-Output "CHECK_${currentCheck}=FAIL"
    Write-Output $_.Exception.ToString()
} finally {
    # Fallback hygiene is explicitly outside the acceptance checks above.
    foreach ($enginePid in $nativeProcessIds) {
        $remaining = Get-CimInstance Win32_Process -Filter "ProcessId = $enginePid" -ErrorAction SilentlyContinue
        if ($remaining -and $remaining.ExecutablePath -eq $exe) {
            Write-Output "TEST HYGIENE ONLY: force stopping test engine PID=$enginePid"
            Stop-Process -Id $enginePid -Force -ErrorAction SilentlyContinue
        }
    }
    $left = Read-Handshake
    if ($left -and $nativeProcessIds.Contains([int]$left.pid)) {
        Write-Output 'TEST HYGIENE ONLY: deleting owned leftover handshake; not an acceptance pass.'
        Remove-Item -LiteralPath $hsPath
    }
    $env:PATH = $savedPath
    [ordered]@{
        started_at = $testStarted.ToString('o'); finished_at = [DateTime]::UtcNow.ToString('o')
        checks = $results; timings_ms = $timings; failed_check = $(if ($script:failed) { $currentCheck } else { $null })
        cold_machine_verified = $false; external_python_required_at_runtime = $false
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stepRoot 'selfcheck-results.json') -Encoding utf8NoBOM
    Stop-Transcript | Out-Null
}
if ($script:failed) { exit 1 }
