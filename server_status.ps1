# Check whether the JobHunt Finland FastAPI server is running on port 8006.

$Port = 8006
$Existing = netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)"

if ($Existing) {
    $PidOnPort = $Existing.Matches[0].Groups[1].Value
    Write-Host "Server is running on http://127.0.0.1:$Port/ (PID $PidOnPort)" -ForegroundColor Green
} else {
    Write-Host "Server is not running on port $Port." -ForegroundColor Red
}
