# Stop the JobHunt Finland FastAPI server running on port 8006.

$Port = 8006
$Existing = netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)"

if (-not $Existing) {
    Write-Host "No server found on port $Port." -ForegroundColor Yellow
    exit 0
}

$PidOnPort = $Existing.Matches[0].Groups[1].Value
try {
    Stop-Process -Id $PidOnPort -Force -ErrorAction Stop
    Write-Host "Stopped server on port $Port (PID $PidOnPort)." -ForegroundColor Green
} catch {
    Write-Host "Failed to stop server (PID $PidOnPort): $_" -ForegroundColor Red
    exit 1
}
