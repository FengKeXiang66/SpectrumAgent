$ErrorActionPreference = 'Stop'
$task25Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
Set-Location -LiteralPath $task25Root
$task25Before = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'before-anchors.txt') -Raw
$task25After = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'after-anchors.txt') -Raw
'Anchors_equal=' + ($task25Before -ceq $task25After)
if ($task25Before -cne $task25After) { throw 'Anchor drift: stop for task-card keeper' }
git diff --exit-code HEAD -- backend src src-python/spectrumagent src-tauri TASK-25-数据集列表与回收站.md
if ($LASTEXITCODE -ne 0) { throw 'Unexpected production/task-card change' }
'Production_and_task_card_diff=0'
$task25ExistingTests = @(git diff --name-only HEAD -- backend/tests src-python/tests src)
'Existing_tracked_tests_diff=' + $task25ExistingTests.Count
if ($task25ExistingTests.Count -ne 0) { throw 'Existing tests changed' }
$task25WriteFiles = @(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'after-write-files.txt'))
'Production_write_files=' + $task25WriteFiles.Count
$task25DTests = @(Get-ChildItem -LiteralPath src-python/tests/storage -Filter test_task25_acceptance.py)
'New_D_test_file=' + $task25DTests[0].FullName
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Whitespace check failed' }
'Tracked_diff_check=PASS'
