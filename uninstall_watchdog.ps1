# Remove the JobHunt Finland watchdog scheduled task.

$TaskName = "JobHuntWatchdog"
schtasks /delete /tn $TaskName /f
if ($?) {
    Write-Host "Removed scheduled task '$TaskName'." -ForegroundColor Green
} else {
    Write-Host "Task '$TaskName' not found or could not be removed." -ForegroundColor Yellow
}
