# Start the JobHunt Finland FastAPI server as a detached background process.
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

# Use WMI so the server is fully detached from this PowerShell window/job.
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Cmd = 'cmd.exe /c cd /d ' + $Root + ' && ' + $Python + ' -m uvicorn src.main:app --host 127.0.0.1 --port ' + $Port + ' > logs\uvicorn.log 2> logs\uvicorn.err.log'
$Proc = Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList $Cmd, $Root

if ($Proc.ReturnValue -ne 0) {
    Write-Host "Failed to start server (WMI return value $($Proc.ReturnValue))." -ForegroundColor Red
    exit 1
}

# Uvicorn binds the port after the lifespan startup fetch completes, which can take ~30-60s.
Write-Host "Waiting for the first fetch to finish and the port to come up..." -ForegroundColor Cyan
$Timeout = 120
$Elapsed = 0
while ($Elapsed -lt $Timeout) {
    Start-Sleep -Seconds 2
    $Elapsed += 2
    $Check = netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)"
    if ($Check) {
        Write-Host "Server started successfully on http://127.0.0.1:$Port/ (PID $($Check.Matches[0].Groups[1].Value))" -ForegroundColor Green
        exit 0
    }
}

Write-Host "Server did not bind to port $Port within ${Timeout}s. It may still be starting; check logs/uvicorn.err.log" -ForegroundColor Yellow
