# JobHunt Finland watchdog (Windows).
# Checks whether the dashboard port is listening; restarts the server if not.
# Intended to run every few minutes via Task Scheduler (see install_watchdog.ps1).

$Port = 8006
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Logs = Join-Path $Root "logs"
$LogFile = Join-Path $Logs "watchdog.log"

if (-not (Test-Path $Logs)) {
    New-Item -ItemType Directory -Path $Logs -Force | Out-Null
}

$Listening = netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)"
if ($Listening) {
    exit 0
}

$Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content $LogFile "$Stamp Port $Port not listening; restarting server..."
& (Join-Path $Root "start_server.ps1") | Out-Null
$Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
if (netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)") {
    Add-Content $LogFile "$Stamp Restart succeeded."
} else {
    Add-Content $LogFile "$Stamp Restart did not bind the port yet (server may still be starting)."
}
