# Install the JobHunt Finland watchdog as a Windows Scheduled Task.
# The task runs every 5 minutes as the current user and restarts the server
# if the dashboard port is not listening.

$TaskName = "JobHuntWatchdog"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Script = Join-Path $Root "watchdog.ps1"
$Action = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Script`""

schtasks /create /tn $TaskName /tr $Action /sc minute /mo 5 /f
if ($?) {
    Write-Host "Installed scheduled task '$TaskName' (runs every 5 minutes)." -ForegroundColor Green
    Write-Host "Remove it later with: .\uninstall_watchdog.ps1" -ForegroundColor Cyan
} else {
    Write-Host "Failed to install the scheduled task." -ForegroundColor Red
    exit 1
}
