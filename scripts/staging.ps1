param(
  [ValidateSet("config","up","down","reset","status","migrate")]
  [string]$Action = "status",
  [switch]$Build,
  [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root "deploy/.env.staging"
$compose = Join-Path $root "deploy/docker-compose.staging.yml"
if (-not (Test-Path $envFile)) { throw "missing deploy/.env.staging; copy from .env.staging.example" }
$text = Get-Content $envFile -Raw
if ($text -notmatch '(?m)^SCIPAL_ENV=staging\s*$') { throw "SCIPAL_ENV must be staging" }
$dsnLines = Select-String -Path $envFile -Pattern '^SCIPAL_[A-Z0-9_]*DSN=' | ForEach-Object { $_.Line }
if (-not $dsnLines) { throw "no staging DSNs found" }
foreach ($line in $dsnLines) {
  if ($line -notmatch 'scipal_staging_') { throw "DSN does not target scipal_staging_*: $line" }
}
if ($text -match '(?m)^SCIPAL_ENV=production\s*$') { throw "production env is forbidden" }
$common = @("-p","scipal-staging","-f",$compose,"--env-file",$envFile)
switch ($Action) {
  "config" { & docker compose @common config }
  "up" {
    if ($Build) { & docker compose @common up -d --build } else { & docker compose @common up -d }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & docker compose @common ps
  }
  "down" { & docker compose @common down }
  "reset" {
    Write-Warning "reset deletes staging volumes; production is untouched"
    & docker compose @common down -v
  }
  "migrate" {
    & $Python scripts/migration_status.py --check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
  "status" {
    & docker compose @common ps
    try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:5002/api/health).Content } catch { Write-Warning "staging app not healthy: $($_.Exception.Message)" }
  }
}
