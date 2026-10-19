$ErrorActionPreference='Stop'
$root='E:\AI_Agent'
Set-Location -LiteralPath $root
$env:CARGO_HOME="$root\.cargo-home"
$env:CARGO_TARGET_DIR="$root\src-tauri\target\milestone03"
$env:CARGO_NET_OFFLINE='true'
$env:TEMP="$root\.runtime\m03-temp"
$env:TMP=$env:TEMP
$env:PATH="$root\.toolchains\node24.19.0-npm10.8.2;$env:PATH"
$env:npm_config_cache="$root\.npm-cache"
$env:npm_config_prefix="$root\.runtime\m03-npm-prefix"
$env:npm_config_strict_ssl='true'
Remove-Item Env:RUSTFLAGS -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $env:TEMP,$env:npm_config_prefix | Out-Null
$evidence="$root\milestone03\evidence\P4"
$cacheSource="$root\src-tauri\target\.tauri"
$cacheTarget="$env:CARGO_TARGET_DIR\.tauri"
if(Test-Path -LiteralPath $cacheTarget){throw 'New tools cache already exists; do not overwrite unknown content'}
Copy-Item -LiteralPath $cacheSource -Destination $cacheTarget -Recurse
$copyInventory=@(Get-ChildItem -LiteralPath $cacheSource -File -Recurse | ForEach-Object {
  $relative=[IO.Path]::GetRelativePath($cacheSource,$_.FullName)
  $copied=Join-Path $cacheTarget $relative
  $before=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  $after=(Get-FileHash -LiteralPath $copied -Algorithm SHA256).Hash.ToLowerInvariant()
  if($before -ne $after){throw "Tools cache mismatch: $relative"}
  [ordered]@{path=$relative; bytes=$_.Length; sha256=$after}
})
$copyInventory | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$evidence\tools-cache-copy.json" -Encoding UTF8
$environment=[ordered]@{CARGO_HOME=$env:CARGO_HOME;CARGO_TARGET_DIR=$env:CARGO_TARGET_DIR;TEMP=$env:TEMP;TMP=$env:TMP;RUSTFLAGS=$env:RUSTFLAGS;CARGO_NET_OFFLINE=$env:CARGO_NET_OFFLINE;node=(& "$root\.toolchains\node24.19.0-npm10.8.2\node.exe" --version);rustc=(& 'C:\Users\Administrator\.cargo\bin\rustc.exe' --version);features='custom-protocol';test_probes=$false;tool_reuse='byte-identical existing official cache, no install/download requested'}
$environment | ConvertTo-Json | Set-Content -LiteralPath "$evidence\build-environment.json" -Encoding UTF8
$log="$evidence\release-build.txt"
'COMMAND: E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\node.exe E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\node_modules\npm\bin\npm-cli.js run tauri -- build --features custom-protocol --bundles nsis --ci --no-binary-patching --runner C:\Users\Administrator\.cargo\bin\cargo.exe -- --locked --offline' | Set-Content -LiteralPath $log -Encoding UTF8
"RUSTFLAGS=$env:RUSTFLAGS" | Add-Content -LiteralPath $log -Encoding UTF8
$started=[DateTime]::UtcNow
& "$root\.toolchains\node24.19.0-npm10.8.2\node.exe" "$root\.toolchains\node24.19.0-npm10.8.2\node_modules\npm\bin\npm-cli.js" run tauri -- build --features custom-protocol --bundles nsis --ci --no-binary-patching --runner C:\Users\Administrator\.cargo\bin\cargo.exe -- --locked --offline *>> $log
$buildExit=$LASTEXITCODE
"EXIT_CODE=$buildExit" | Add-Content -LiteralPath $log -Encoding UTF8
@{command_log=$log;exit_code=$buildExit;started_utc=$started.ToString('o');finished_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath "$evidence\build-execution.json" -Encoding UTF8
Get-Content -LiteralPath $log -Tail 22
exit $buildExit
