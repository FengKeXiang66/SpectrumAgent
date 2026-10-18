# Generate the sealed Step-2 product inventory, outside the product tree.
# No build, installation, engine launch, or mutation of dist/app is performed.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$artifactRoot = Join-Path $projectRoot 'artifacts\step2\dist\app'
$outputPath = Join-Path $PSScriptRoot 'product-manifest.json'
if (Test-Path -LiteralPath $outputPath) { throw 'Refusing to overwrite the authoritative product manifest.' }

$generatorCommit = git -C $projectRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot read generator HEAD.' }
git -C $projectRoot diff --quiet d218262 -- backend requirements-lock.txt artifacts/step2/build.spec
if ($LASTEXITCODE -ne 0) { throw 'Backend, lock or spec differs from artifact source commit d218262.' }

$sourceManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'source-manifest.json') -Raw | ConvertFrom-Json
foreach ($entry in $sourceManifest.source_sha256.PSObject.Properties) {
    $actual = (Get-FileHash -LiteralPath (Join-Path $projectRoot $entry.Name) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $entry.Value) { throw "Source evidence hash mismatch: $($entry.Name)" }
}

$rootItem = Get-Item -LiteralPath $artifactRoot -Force
$allItems = @($rootItem) + @(Get-ChildItem -LiteralPath $artifactRoot -Recurse -Force)
if (@($allItems | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) {
    throw 'Reparse points are not permitted in the sealed product tree.'
}
$suspicious = @($allItems | Where-Object {
    $_.Name -match '(?i)(\.test-backup|\.(tmp|temp|bak|backup|part)$|^(manifest|fault_fixture|fault-fixture|fixture)([._-]|$))'
})
if ($suspicious.Count) { throw ('Experimental residue: ' + ($suspicious.FullName -join ', ')) }
$topNames = @(Get-ChildItem -LiteralPath $artifactRoot -Force | Select-Object -ExpandProperty Name | Sort-Object)
if (($topNames -join '|') -cne '_internal|app.exe') { throw 'Unexpected top-level product layout.' }

$exe = Get-Item -LiteralPath (Join-Path $artifactRoot 'app.exe')
$internalRoot = Join-Path $artifactRoot '_internal'
$files = @(Get-ChildItem -LiteralPath $artifactRoot -Recurse -File -Force)
$internalFiles = @(Get-ChildItem -LiteralPath $internalRoot -Recurse -File -Force)
$internalBytes = [long]($internalFiles | Measure-Object -Property Length -Sum).Sum
$exeHash = (Get-FileHash -LiteralPath $exe.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$dllCount = @(Get-ChildItem -LiteralPath (Join-Path $internalRoot 'rasterio.libs') -File -Filter '*.dll').Count
$pydCount = @(Get-ChildItem -LiteralPath (Join-Path $internalRoot 'rasterio') -Recurse -File -Filter '*.pyd').Count
if ($exe.Length -ne 16771126) { throw "EXE bytes mismatch: $($exe.Length)" }
if ($exeHash -cne $sourceManifest.exe_sha256) { throw 'EXE SHA256 differs from source-manifest.json.' }
if ($internalFiles.Count -ne 543 -or $internalBytes -ne 238793334) {
    throw "Internal inventory mismatch: $($internalFiles.Count) files / $internalBytes bytes"
}
if (-not (Test-Path -LiteralPath (Join-Path $internalRoot 'python312.dll') -PathType Leaf)) { throw 'python312.dll missing.' }
if ($dllCount -ne 36 -or $pydCount -ne 15) { throw "Rasterio inventory mismatch: $dllCount DLL / $pydCount pyd" }
if ($files.Count -ne 544) { throw "Total file count mismatch: $($files.Count)" }

$byPath = @{}
$sortedPaths = [Collections.Generic.List[string]]::new()
foreach ($file in $files) {
    $relative = [IO.Path]::GetRelativePath($artifactRoot, $file.FullName).Replace('\', '/')
    $sortedPaths.Add($relative)
    $byPath[$relative] = [ordered]@{
        path = $relative
        bytes = [long]$file.Length
        sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$sortedPaths.Sort([StringComparer]::Ordinal)
$manifest = [ordered]@{
    schema_version = 1
    artifact_source_commit = 'd218262'
    manifest_generated_at = [DateTime]::UtcNow.ToString('o')
    manifest_generator_commit = $generatorCommit.Trim()
    artifact_root = 'artifacts/step2/dist/app'
    files = @($sortedPaths | ForEach-Object { $byPath[$_] })
}
# CreateNew preserves a previously generated authority even on a racing invocation.
$jsonBytes = [Text.UTF8Encoding]::new($false).GetBytes(($manifest | ConvertTo-Json -Depth 6) + "`n")
$stream = [IO.File]::Open($outputPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $stream.Write($jsonBytes, 0, $jsonBytes.Length) } finally { $stream.Dispose() }

[ordered]@{
    event = 'product_manifest_generated'
    artifact_source_commit = $manifest.artifact_source_commit
    manifest_generator_commit = $manifest.manifest_generator_commit
    exe_bytes = $exe.Length
    exe_sha256 = $exeHash
    internal_files = $internalFiles.Count
    internal_bytes = $internalBytes
    python312_exists = $true
    rasterio_libs_dll = $dllCount
    rasterio_pyd = $pydCount
    experimental_residue = $suspicious.Count
    total_files = $files.Count
    product_manifest_sha256 = (Get-FileHash -LiteralPath $outputPath -Algorithm SHA256).Hash.ToLowerInvariant()
} | ConvertTo-Json
