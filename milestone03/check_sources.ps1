$ErrorActionPreference='Stop'
$root='E:\AI_Agent'
Set-Location -LiteralPath $root
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH="$root;$root\src-python"
$env:CARGO_HOME="$root\.cargo-home"
$env:CARGO_TARGET_DIR="$root\src-tauri\target\milestone03"
$env:CARGO_NET_OFFLINE='true'
$env:TEMP="$root\.runtime\m03-temp"
$env:TMP=$env:TEMP
$env:PATH="$root\.toolchains\node24.19.0-npm10.8.2;$env:PATH"
Remove-Item Env:RUST_TEST_THREADS,Env:RUSTFLAGS -ErrorAction SilentlyContinue
$evidence="$root\milestone03\evidence\P5"
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
@{TEMP=$env:TEMP;TMP=$env:TMP;CARGO_HOME=$env:CARGO_HOME;CARGO_TARGET_DIR=$env:CARGO_TARGET_DIR;RUST_TEST_THREADS=$env:RUST_TEST_THREADS;cargo_test_mode='default parallel, no --test-threads';PYTHONPATH=$env:PYTHONPATH} | ConvertTo-Json | Set-Content -LiteralPath "$evidence\environment.json" -Encoding UTF8
$results=[Collections.Generic.List[object]]::new()
function Invoke-Check([string]$Check,[string]$Executable,[string[]]$CommandArguments){
  $log="$evidence\$Check.txt"
  if(Test-Path -LiteralPath $log){throw "Refuse previous output overwrite: $Check"}
  "COMMAND: $Executable $($CommandArguments -join ' ')" | Set-Content -LiteralPath $log -Encoding UTF8
  & $Executable @CommandArguments *>> $log
  $checkExit=$LASTEXITCODE
  "EXIT_CODE=$checkExit" | Add-Content -LiteralPath $log -Encoding UTF8
  $results.Add(@{check=$Check;exit_code=$checkExit;command="$Executable $($CommandArguments -join ' ')"})
  $results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$evidence\results.json" -Encoding UTF8
  Get-Content -LiteralPath $log -Tail 8
  if($checkExit -ne 0){throw "P5 STOP: $Check exit $checkExit"}
}
$python="$root\.venv\Scripts\python.exe"
$cargo='C:\Users\Administrator\.cargo\bin\cargo.exe'
$node="$root\.toolchains\node24.19.0-npm10.8.2\node.exe"
Invoke-Check 'pytest' $python @('-m','pytest','backend/tests','src-python/tests','-q','--basetemp',"$root\.runtime\m03-temp\pytest")
Invoke-Check 'cargo-test-default' $cargo @('test','--manifest-path',"$root\src-tauri\Cargo.toml",'--locked','--offline')
Invoke-Check 'node-test' $node @('--test','src/components/datasets/types.test.ts')
Invoke-Check 'tsc' $node @('node_modules/typescript/bin/tsc','--noEmit')
Invoke-Check 'clippy' $cargo @('clippy','--manifest-path',"$root\src-tauri\Cargo.toml",'--locked','--offline','--all-targets','--','-D','warnings')
Invoke-Check 'vite' $node @('node_modules/vite/bin/vite.js','build')
'P5 ALL COMMANDS EXIT 0'
