param(
  [ValidateSet("start","check","finish","status","staging","help")]
  [string]$Action = "help",
  [string]$Task = "",
  [string]$EnvFile = "",
  [string]$Python = "python",
  [switch]$Quick,
  [switch]$Local
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot

function Load-EnvFile([string]$path) {
  if (-not $path) { return }
  if (-not (Test-Path $path)) { throw "env file not found: $path" }
  foreach ($line in Get-Content $path) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $name, $value = $line.Split('=', 2)
    if ($name -notmatch '_DSN$' -and $name -notin @('SCIPAL_INTERNAL_TOKEN','SCIPAL_SECRET_KEY')) { continue }
    if ($Local) { $value = $value -replace '@scipal-pg:', '@127.0.0.1:' -replace '@host.docker.internal:', '@127.0.0.1:' }
    if ($name -match '^[A-Za-z_][A-Za-z0-9_]*$') {
      Set-Item -Path "Env:$name" -Value $value
    }
  }
  Write-Host "ENV_LOADED $path"
}

function Resolve-EnvFile() {
  if ($EnvFile) { return $EnvFile }
  if ($env:SCIPAL_ENV_FILE) { return $env:SCIPAL_ENV_FILE }
  foreach ($candidate in @("$root\deploy\.env", "$root\.env")) {
    if (Test-Path $candidate) { return $candidate }
  }
  return ""
}

function Invoke-Check {
  $envPath = Resolve-EnvFile
  if ($envPath) { Load-EnvFile $envPath }
  & "$root\scripts\local_gate.ps1" -Python $Python
  if ($LASTEXITCODE -ne 0) { throw "local gate failed" }
  if (-not $Quick) {
    & $Python -m unittest discover -s "$root\tests" -p "test_*.py"
    if ($LASTEXITCODE -ne 0) { throw "tests failed" }
  }
  Write-Host "SOLO_CHECK_OK"
}

switch ($Action) {
  "start" {
    if (-not $Task) { throw "usage: solo.ps1 start <task-name>" }
    & $Python "$root\scripts\worktree.py" new $Task --base dev
    if ($LASTEXITCODE -ne 0) { throw "worktree creation failed" }
    Write-Host "NEXT: cd $root\.worktrees\$Task"
  }
  "check" { Invoke-Check }
  "finish" {
    Invoke-Check
    Write-Host "--- diff ---"
    git -C $root diff --stat
    Write-Host "NEXT:"
    Write-Host "  git add -A"
    Write-Host "  git commit -m `"<one-line change>`""
    Write-Host "  git push -u origin HEAD"
    Write-Host "  open PR to dev"
  }
  "status" {
    Write-Host "--- branch ---"
    git -C $root rev-parse --abbrev-ref HEAD
    Write-Host "--- status ---"
    git -C $root status --short
    Write-Host "--- worktrees ---"
    & $Python "$root\scripts\worktree.py" list
  }
  "staging" {
    & "$root\scripts\staging.ps1" -Action up -Python $Python
  }
  default {
    Write-Host "solo.ps1 <start|check|finish|status|staging> [options]"
    Write-Host "  start <task>    create .worktrees/<task> + task/<task>"
    Write-Host "  check           local_gate + full tests (use -Quick for gates only)"
    Write-Host "  finish          check + print commit/PR steps"
    Write-Host "  status          branch/status/worktrees"
    Write-Host "  staging         start staging stack"
    Write-Host "  -EnvFile PATH   load DSNs/secrets for gates"
    Write-Host "  -Python PATH    python executable"
  }
}
