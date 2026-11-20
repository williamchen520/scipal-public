param(
  [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "== code budget =="
& $Python scripts/code_budget.py --strict
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "== plugins =="
& $Python scripts/check_plugins.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "== import boundaries =="
& $Python scripts/check_import_boundaries.py --strict
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "== migrations =="
& $Python scripts/migration_status.py --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "== domains =="
& $Python scripts/check_domains.py --strict
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "== route manifest =="
& $Python scripts/export_routes.py --check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "LOCAL_GATE_OK"
