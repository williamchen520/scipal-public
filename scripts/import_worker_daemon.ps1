# Import worker supervisor: restarts the worker if it exits.
param(
  [int]$IntervalSeconds = 5,
  [string]$Log = "D:\sciPal\logs\import_worker.log"
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "venv_sciPal_py312\Scripts\python.exe"
New-Item -ItemType Directory -Force (Split-Path -Parent $Log) | Out-Null

while ($true) {
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "[$stamp] worker start" | Add-Content -Path $Log -Encoding UTF8
  & $Python (Join-Path $Root "scripts\import_worker.py") --loop --interval $IntervalSeconds *>> $Log
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "[$stamp] worker exited; restart in 10s" | Add-Content -Path $Log -Encoding UTF8
  Start-Sleep -Seconds 10
}
