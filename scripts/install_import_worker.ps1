# Register the import worker supervisor at user logon.
param(
  [string]$TaskName = "SciPalImportWorker"
)

$Root = Split-Path -Parent $PSScriptRoot
$Daemon = Join-Path $Root "scripts\import_worker_daemon.ps1"
$Command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Daemon`""

schtasks.exe /Create /SC ONLOGON /TN $TaskName /TR $Command /F
