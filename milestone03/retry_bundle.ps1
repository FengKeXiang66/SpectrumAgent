$ErrorActionPreference='Stop'
Set-Location -LiteralPath 'E:\AI_Agent'
$env:CARGO_HOME='E:\AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR='E:\AI_Agent\src-tauri\target\milestone03'
$env:CARGO_NET_OFFLINE='true'
$env:TEMP='E:\AI_Agent\.runtime\m03-temp'
$env:TMP=$env:TEMP
$env:PATH="E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2;$env:PATH"
$env:npm_config_cache='E:\AI_Agent\.npm-cache'
$env:npm_config_prefix='E:\AI_Agent\.runtime\m03-npm-prefix'
Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:ALL_PROXY,Env:RUSTFLAGS -ErrorAction SilentlyContinue
$env:NO_PROXY='*'
$log='E:\AI_Agent\milestone03\evidence\P4\bundle-retry.txt'
if(Test-Path -LiteralPath $log){throw 'Preserve prior output'}
'COMMAND: E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\node.exe E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\node_modules\npm\bin\npm-cli.js run tauri -- bundle --features custom-protocol --bundles nsis --ci --no-binary-patching --verbose' | Set-Content -LiteralPath $log -Encoding UTF8
'CHANNEL: env proxy variables removed in this process; NO_PROXY=*; TLS verification unchanged. Existing custom-protocol release build reused.' | Add-Content -LiteralPath $log -Encoding UTF8
& 'E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\node.exe' 'E:\AI_Agent\.toolchains\node24.19.0-npm10.8.2\node_modules\npm\bin\npm-cli.js' run tauri -- bundle --features custom-protocol --bundles nsis --ci --no-binary-patching --verbose *>> $log
$bundleExit=$LASTEXITCODE
"EXIT_CODE=$bundleExit" | Add-Content -LiteralPath $log -Encoding UTF8
Get-Content -LiteralPath $log -Tail 25
exit $bundleExit
