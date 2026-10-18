param([Parameter(ValueFromRemainingArguments=$true)][string[]]$NpmArguments)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$toolchainDir = Join-Path $PSScriptRoot '.toolchains\node24.19.0-npm10.8.2'
$nodeExe = Join-Path $toolchainDir 'node.exe'
$npmCli = Join-Path $toolchainDir 'node_modules\npm\bin\npm-cli.js'
if ((Get-FileHash -LiteralPath $nodeExe -Algorithm SHA256).Hash -ne '3602F2BB1A10F2CBAB4C36886218A33C1AB3DB87290E73B033C46C77147D0237') { throw 'Node 指纹与已批准工具链不符' }
$env:PATH = "$toolchainDir;$env:PATH"
$env:npm_config_cache = Join-Path $PSScriptRoot '.npm-cache'
$env:npm_config_prefix = $toolchainDir
$env:npm_config_strict_ssl = 'true'
$env:CARGO_HOME = Join-Path $PSScriptRoot '.cargo-home'
$env:CARGO_TARGET_DIR = Join-Path $PSScriptRoot 'src-tauri\target'
$env:TEMP = Join-Path $PSScriptRoot 'artifacts\step3\checkpoint-3\temp'
$env:TMP = $env:TEMP
if ($env:NODE_TLS_REJECT_UNAUTHORIZED -eq '0') { throw '现有环境禁用了 TLS 校验，拒绝继续' }
Set-Location -LiteralPath $PSScriptRoot
# PowerShell can consume an unquoted -- at the script boundary. npm needs its
# own delimiter to forward flags such as --no-watch/--help to package scripts.
if ($NpmArguments.Count -gt 2 -and $NpmArguments[0] -eq 'run' -and $NpmArguments[2] -ne '--') {
    $NpmArguments = @($NpmArguments[0], $NpmArguments[1], '--') + $NpmArguments[2..($NpmArguments.Count - 1)]
}
& $nodeExe $npmCli @NpmArguments
exit $LASTEXITCODE
