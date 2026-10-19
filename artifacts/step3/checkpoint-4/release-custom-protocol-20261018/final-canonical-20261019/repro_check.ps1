$ErrorActionPreference='Stop'
$repo='E:\AI_Agent'
$out=$PSScriptRoot
$target=Join-Path $repo 'src-tauri\target\repro-check'
if(Test-Path -LiteralPath $target){throw 'Independent repro target already exists; do not reuse unknown build state'}
$env:CARGO_HOME=Join-Path $repo '.cargo-home'
$env:CARGO_TARGET_DIR=$target
$env:CARGO_NET_OFFLINE='true'
$env:RUSTFLAGS=''
$env:TEMP=Join-Path $repo 'artifacts\step3\checkpoint-4\temp'
$env:TMP=$env:TEMP
$nodeDir=Join-Path $repo '.toolchains\node24.19.0-npm10.8.2'
$env:PATH=$nodeDir+';'+$env:PATH
$env:npm_config_cache=Join-Path $repo '.npm-cache'
$env:npm_config_strict_ssl='true'
function Record([string]$Name,$Value){
 $path=Join-Path $out $Name
 if(Test-Path -LiteralPath $path){throw "Evidence already exists: $path"}
 [IO.File]::WriteAllText($path,($Value|ConvertTo-Json -Depth 12)+"`n",[Text.UTF8Encoding]::new($false))
 Get-Content -LiteralPath $path -Raw
}
function Dist-Tree {
 $dist=Join-Path $repo 'dist'
 @(Get-ChildItem -LiteralPath $dist -File -Recurse|Sort-Object FullName|ForEach-Object {
 [ordered]@{path=[IO.Path]::GetRelativePath($dist,$_.FullName).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
 })
}
$old=Join-Path $repo 'src-tauri\target\release'
$baseline=Join-Path $old 'spectrum-agent.exe'
$expected='22a13e6a4d2ec88cf58fa349aad7f22e61fa11331adca11e11eec9c781f73471'
if((Get-FileHash -LiteralPath $baseline).Hash.ToLowerInvariant() -cne $expected){throw 'Baseline exe differs from approved 22a13e6a'}
$rustc=& 'C:\Users\Administrator\.cargo\bin\rustc.exe' -Vv
if($LASTEXITCODE -ne 0 -or $rustc[0] -cne 'rustc 1.99.1 (58cf8f9c3 2026-10-13)'){throw 'Rust version differs'}
Write-Output ('$env:RUSTFLAGS=['+[string]$env:RUSTFLAGS+']')
Record 'repro-build-conditions.json' ([ordered]@{started_utc=[DateTime]::UtcNow.ToString('o');rustc=$rustc;profile='release';features='custom-protocol';RUSTFLAGS=[string]$env:RUSTFLAGS;CARGO_HOME=$env:CARGO_HOME;CARGO_TARGET_DIR=$env:CARGO_TARGET_DIR;TEMP=$env:TEMP;baseline_sha256=$expected;source_commit='a53030d47fc169ddfa67057e45c464fc0f1db2cd';source_diff=@(git diff a53030d HEAD -- src-tauri/src src-tauri/Cargo.toml src-tauri/Cargo.lock src-tauri/tauri.conf.json src-tauri/build.rs src-tauri/nsis src package.json);cache_policy='copy dependency artifacts only; all spectrum-agent own fingerprints/build outputs/deps excluded; own crate truly recompiles'})
Record 'repro-dist-before.json' (Dist-Tree)
New-Item -ItemType Directory -Path (Join-Path $target 'release')|Out-Null
# Reuse dependencies, not any project code artifacts. The independent main exe
# cannot exist before cargo and this is asserted immediately before compilation.
foreach($name in @('.fingerprint','build')){
 $destination=Join-Path $target ('release\'+$name)
 New-Item -ItemType Directory -Path $destination|Out-Null
 foreach($item in Get-ChildItem -LiteralPath (Join-Path $old $name) -Force){
  if($item.Name -notlike 'spectrum-agent-*'){Copy-Item -LiteralPath $item.FullName -Destination $destination -Recurse}
 }
}
$deps=Join-Path $target 'release\deps'
New-Item -ItemType Directory -Path $deps|Out-Null
foreach($item in Get-ChildItem -LiteralPath (Join-Path $old 'deps') -File -Force){
 if($item.Name -notlike 'spectrum_agent*'){Copy-Item -LiteralPath $item.FullName -Destination $deps}
}
Set-Location -LiteralPath $repo
& (Join-Path $nodeDir 'node.exe') (Join-Path $nodeDir 'node_modules\npm\bin\npm-cli.js') run build
if($LASTEXITCODE -ne 0){throw 'Repro frontend build failed'}
$exe=Join-Path $target 'release\spectrum-agent.exe'
if(Test-Path -LiteralPath $exe){throw 'Own exe unexpectedly existed before compilation'}
Write-Output 'COMMAND: cargo build --manifest-path E:\AI_Agent\src-tauri\Cargo.toml --release --features custom-protocol --bin spectrum-agent --locked --offline --verbose'
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' build --manifest-path (Join-Path $repo 'src-tauri\Cargo.toml') --release --features custom-protocol --bin spectrum-agent --locked --offline --verbose
if($LASTEXITCODE -ne 0){throw 'True independent Rust rebuild failed'}
Record 'repro-dist-after.json' (Dist-Tree)
$distEqual=[IO.File]::ReadAllText((Join-Path $out 'repro-dist-before.json')) -ceq [IO.File]::ReadAllText((Join-Path $out 'repro-dist-after.json'))
Record 'repro-build-result.json' ([ordered]@{finished_utc=[DateTime]::UtcNow.ToString('o');exe=$exe;bytes=(Get-Item -LiteralPath $exe).Length;sha256=(Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant();baseline_sha256=$expected;baseline_unchanged=((Get-FileHash -LiteralPath $baseline).Hash.ToLowerInvariant() -ceq $expected);byte_identical=((Get-FileHash -LiteralPath $exe).Hash.ToLowerInvariant() -ceq $expected);dist_full_manifest_identical=$distEqual})
if(-not $distEqual){throw 'Frontend dist changed; investigate before accepting rebuild'}
