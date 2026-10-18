$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = 'E:\AI_Agent'
$toolchainDir = Join-Path $root '.toolchains\node24.19.0-npm10.8.2'
$nodeExe = Join-Path $toolchainDir 'node.exe'
$npmCli = Join-Path $toolchainDir 'node_modules\npm\bin\npm-cli.js'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
Set-Location -LiteralPath $root
if ((Get-FileHash -LiteralPath $nodeExe -Algorithm SHA256).Hash -ne '3602F2BB1A10F2CBAB4C36886218A33C1AB3DB87290E73B033C46C77147D0237') { throw 'Node 指纹不符合已批准值' }
$userPathBefore = [Environment]::GetEnvironmentVariable('PATH', 'User')
$machinePathBefore = [Environment]::GetEnvironmentVariable('PATH', 'Machine')
$env:PATH = "$toolchainDir;$env:PATH"
$env:npm_config_cache = Join-Path $root '.npm-cache'
$env:npm_config_prefix = $toolchainDir
$env:npm_config_strict_ssl = 'true'
$env:npm_config_audit = 'false'
$env:npm_config_fund = 'false'
$env:npm_config_fetch_retries = '0'
$env:npm_config_fetch_timeout = '30000'
$env:CARGO_HOME = Join-Path $root '.cargo-home'
$env:CARGO_TARGET_DIR = Join-Path $root 'src-tauri\target'
$env:TEMP = Join-Path $PSScriptRoot 'temp'
$env:TMP = $env:TEMP
if ($env:NODE_TLS_REJECT_UNAUTHORIZED -eq '0') { throw '现有环境禁用了 TLS 校验，停止安装' }
if ((& $nodeExe --version) -ne 'v24.19.0') { throw 'Node 版本不符合批准值' }
if ((& $nodeExe $npmCli --version) -ne '10.8.2') { throw 'npm 版本不符合批准值' }
$proposed = Join-Path $PSScriptRoot 'package.proposed.json'
$manifest = Join-Path $root 'package.json'
if (Test-Path -LiteralPath $manifest) {
    if ((Get-FileHash -LiteralPath $manifest).Hash -ne (Get-FileHash -LiteralPath $proposed).Hash) { throw '正式 package.json 内容未知，拒绝覆盖' }
} else { Copy-Item -LiteralPath $proposed -Destination $manifest }
Write-Output "node=$nodeExe"
Write-Output "npm_cli=$npmCli"
Write-Output "npm_cache=$env:npm_config_cache"
Write-Output "CARGO_HOME=$env:CARGO_HOME"
Write-Output "CARGO_TARGET_DIR=$env:CARGO_TARGET_DIR"
Write-Output "TEMP=$env:TEMP"
Write-Output "npm_strict_ssl=$env:npm_config_strict_ssl"
$sets = @(
    [pscustomobject]@{name='runtime';args=@('install','--save-exact','--engine-strict','react@19.3.1','react-dom@19.3.1','@tauri-apps/api@2.12.4')},
    [pscustomobject]@{name='dev';args=@('install','--save-dev','--save-exact','--engine-strict','vite@8.3.4','typescript@5.9.3','@vitejs/plugin-react@6.1.2','@types/react@19.3.0','@types/react-dom@19.3.0','@types/node@24.10.1','@tauri-apps/cli@2.12.3')}
)
foreach ($set in $sets) {
    $argsForNpm = $set.args
    $log = Join-Path $PSScriptRoot "npm-$($set.name)-install-$stamp.txt"
    Write-Output "Command: $nodeExe $npmCli $($argsForNpm -join ' ')"
    & $nodeExe $npmCli @argsForNpm 2>&1 | Tee-Object -FilePath $log
    $nativeExit = $LASTEXITCODE
    $record = [pscustomobject]@{
        command = @($nodeExe,$npmCli) + $argsForNpm
        exit_code = $nativeExit
        strict_ssl = $env:npm_config_strict_ssl
        user_PATH_unchanged = $userPathBefore -ceq [Environment]::GetEnvironmentVariable('PATH','User')
        machine_PATH_unchanged = $machinePathBefore -ceq [Environment]::GetEnvironmentVariable('PATH','Machine')
        output_file = $log
    }
    $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot "npm-$($set.name)-execution-$stamp.json") -Encoding utf8
    if ($nativeExit -ne 0) {
        Write-Output "安装失败，按负责人要求停止；原始输出=$log；未关闭证书验证，未尝试绕过。"
        exit $nativeExit
    }
}
