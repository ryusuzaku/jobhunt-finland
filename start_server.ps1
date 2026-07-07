# Start the JobHunt Finland FastAPI server as a background process.
# Logs are written to logs/uvicorn.log and logs/uvicorn.err.log.

$Port = 8006
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Logs = Join-Path $Root "logs"

# Run one-time setup if the virtual environment is missing.
if (-not (Test-Path (Join-Path $Root ".venv"))) {
    & (Join-Path $Root "setup.ps1")
}

if (-not (Test-Path $Logs)) {
    New-Item -ItemType Directory -Path $Logs -Force | Out-Null
}

$Existing = netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)"
if ($Existing) {
    $PidOnPort = $Existing.Matches[0].Groups[1].Value
    Write-Host "Server already running on port $Port (PID $PidOnPort)." -ForegroundColor Yellow
    exit 0
}

Write-Host "Starting uvicorn on port $Port..." -ForegroundColor Green
Start-Process `
    -FilePath (Join-Path $Root ".venv\Scripts\python.exe") `
    -ArgumentList "-m uvicorn src.main:app --host 127.0.0.1 --port $Port --reload" `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Logs "uvicorn.log") `
    -RedirectStandardError (Join-Path $Logs "uvicorn.err.log")

Start-Sleep -Seconds 3

$Check = netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)"
if ($Check) {
    Write-Host "Server started successfully on http://127.0.0.1:$Port/ (PID $($Check.Matches[0].Groups[1].Value))" -ForegroundColor Green
} else {
    Write-Host "Server may have failed to start. Check logs/uvicorn.err.log" -ForegroundColor Red
}
