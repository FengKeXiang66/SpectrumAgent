$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$workspace = 'E:\AI_Agent'
$interpreter = 'E:\AI_Agent\.venv\Scripts\python.exe'
$evidence = Join-Path $workspace 'artifacts\step1'
$dataRoot = Join-Path $env:LOCALAPPDATA 'SpectrumAgent'
$handshakePath = Join-Path $dataRoot 'run\handshake.json'
$engineProcess = $null
$engineIdentity = $null

function Invoke-CurlCheck {
    param([string]$Path, [string]$ExpectedCode, [switch]$Authenticated, [string]$EvidenceName)
    $url = "http://127.0.0.1:$($engineIdentity.port)$Path"
    $bodyPath = Join-Path $evidence "$EvidenceName.json"
    $curlArgs = @('--silent', '--show-error', '--noproxy', '*', '--max-time', '30', '-o', $bodyPath, '-w', '%{http_code}')
    if ($Authenticated) {
        # The generated token stays out of the transcript and structured engine logs.
        $curlArgs += @('-H', "Authorization: Bearer $($engineIdentity.token)")
        Write-Output ('> curl.exe --noproxy "*" -H "Authorization: Bearer $($engineIdentity.token)" ' + $url)
    } else {
        Write-Output ('> curl.exe --noproxy "*" ' + $url)
    }
    $code = & curl.exe @curlArgs $url
    if ($LASTEXITCODE -ne 0) { throw "curl exit code $LASTEXITCODE" }
    $raw = Get-Content -LiteralPath $bodyPath -Raw
    Write-Output "HTTP $code"
    Write-Output $raw.Trim()
    if ($code -ne $ExpectedCode) { throw "Expected HTTP $ExpectedCode, got $code" }
}

try {
    if (Test-Path -LiteralPath $handshakePath) {
        $old = Get-Content -LiteralPath $handshakePath -Raw | ConvertFrom-Json
        $existing = Get-Process -Id $old.pid -ErrorAction SilentlyContinue
        if ($existing) { throw 'Existing handshake PID is alive; inspect it before this selfcheck.' }
    }
    Write-Output '> Start-Process -FilePath E:\AI_Agent\.venv\Scripts\python.exe -ArgumentList @("-m", "backend") -WorkingDirectory E:\AI_Agent -WindowStyle Hidden -PassThru'
    $engineProcess = Start-Process -FilePath $interpreter -ArgumentList @('-m', 'backend') -WorkingDirectory $workspace -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $evidence 'engine-stdout.log') -RedirectStandardError (Join-Path $evidence 'engine-stderr.log')
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([DateTime]::UtcNow -lt $deadline) {
        $engineProcess.Refresh()
        if ($engineProcess.HasExited) { throw "Engine exited: $($engineProcess.ExitCode)" }
        if (Test-Path -LiteralPath $handshakePath) {
            $candidate = Get-Content -LiteralPath $handshakePath -Raw | ConvertFrom-Json
            if (([DateTime]$candidate.process_created_at).ToUniversalTime() -ge $engineProcess.StartTime.ToUniversalTime().AddSeconds(-1)) {
                $engineIdentity = $candidate
                break
            }
        }
        Start-Sleep -Milliseconds 50
    }
    if ($null -eq $engineIdentity) { throw 'Timed out waiting for current handshake.' }
    Write-Output '> Get-Content "$env:LOCALAPPDATA\SpectrumAgent\run\handshake.json" (token omitted)'
    [ordered]@{
        boot_id = $engineIdentity.boot_id; pid = $engineIdentity.pid
        process_created_at = $engineIdentity.process_created_at; port = $engineIdentity.port
        protocol = $engineIdentity.protocol; version = $engineIdentity.version
        started_at = $engineIdentity.started_at; token_length = $engineIdentity.token.Length
    } | ConvertTo-Json -Compress | Write-Output
    $actual = Get-Process -Id $engineIdentity.pid
    $actualTime = $actual.StartTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    $handshakeTime = ([DateTime]$engineIdentity.process_created_at).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ')
    if ($actualTime -ne $handshakeTime) { throw "Creation time mismatch: $actualTime vs $handshakeTime" }
    if ($engineIdentity.token -cnotmatch '^[0-9a-f]{32}$') { throw 'Token is not 32 hex characters.' }
    Write-Output 'PASS: process_created_at matches Windows process creation time; token is 32 hex characters.'

    Invoke-CurlCheck '/health' '200' -EvidenceName 'health'
    $health = Get-Content -LiteralPath (Join-Path $evidence 'health.json') -Raw | ConvertFrom-Json
    if ($health.boot_id -ne $engineIdentity.boot_id -or $health.pid -ne $engineIdentity.pid) { throw 'Health identity mismatch.' }
    Write-Output 'PASS: /health boot_id and pid match handshake.'
    Invoke-CurlCheck '/smoke' '200' -Authenticated -EvidenceName 'smoke'
    $smoke = Get-Content -LiteralPath (Join-Path $evidence 'smoke.json') -Raw | ConvertFrom-Json
    foreach ($field in @('nan_ratio','reflectance_range','bands','shape','elapsed_ms')) {
        if ($field -notin $smoke.PSObject.Properties.Name) { throw "Missing field $field" }
    }
    if ($smoke.nan_ratio -ne 0 -or $smoke.bands -ne 8 -or ($smoke.shape -join ',') -ne '8,8,8') { throw 'Invalid smoke metrics.' }
    Invoke-CurlCheck '/smoke' '401' -EvidenceName 'unauthorized'
    Invoke-CurlCheck '/smoke?blocks=8' '200' -Authenticated -EvidenceName 'smoke-blocks'

    Write-Output '> Get-ChildItem "$env:LOCALAPPDATA\SpectrumAgent\testdata"'
    Get-ChildItem -LiteralPath (Join-Path $dataRoot 'testdata') | ForEach-Object { Write-Output ("{0} {1} bytes" -f $_.Name, $_.Length) }
    $logFile = Join-Path $dataRoot ('logs\engine-' + (Get-Date -Format 'yyyyMMdd') + '.jsonl')
    Write-Output ('> Get-Content "' + $logFile + '" | ForEach-Object { $_ | ConvertFrom-Json }')
    $lines = @(Get-Content -LiteralPath $logFile)
    foreach ($line in $lines) { $null = $line | ConvertFrom-Json }
    $current = @($lines | Where-Object { ($_ | ConvertFrom-Json).boot_id -eq $engineIdentity.boot_id })
    if ($current.Count -eq 0) { throw 'No current boot log records found.' }
    if (($lines -join "`n").Contains($engineIdentity.token)) { throw 'Token leaked to JSON log.' }
    Write-Output "PASS: $($lines.Count) valid JSON lines; $($current.Count) current boot records; no token in log."
    $current | Select-Object -First 3 | Write-Output
} finally {
    # This check deliberately runs an independent process without a shell Job Object.
    # Kill both the venv launcher and actual engine if Windows uses a redirector.
    if ($engineIdentity) {
        Stop-Process -Id $engineIdentity.pid -Force -ErrorAction SilentlyContinue
    }
    if ($engineProcess) {
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($engineProcess.Id)" -ErrorAction SilentlyContinue)
        foreach ($child in $children) {
            Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
        }
        $engineProcess.Refresh()
        if (-not $engineProcess.HasExited) { Stop-Process -Id $engineProcess.Id -Force -ErrorAction SilentlyContinue }
        $null = $engineProcess.WaitForExit(5000)
    }
    if ($engineIdentity) {
        Start-Sleep -Milliseconds 200
        if (Get-Process -Id $engineIdentity.pid -ErrorAction SilentlyContinue) { throw 'Engine process remains after selfcheck.' }
        $listener = Get-NetTCPConnection -State Listen -LocalPort $engineIdentity.port -ErrorAction SilentlyContinue
        if ($listener) { throw 'Engine port remains listening after selfcheck.' }
        if (Test-Path -LiteralPath $handshakePath) {
            $last = Get-Content -LiteralPath $handshakePath -Raw | ConvertFrom-Json
            if ($last.boot_id -eq $engineIdentity.boot_id) { Remove-Item -LiteralPath $handshakePath }
        }
        Write-Output 'PASS: independent selfcheck engine stopped; PID and listening port absent; owned handshake cleaned by harness.'
    }
}
