# Start the self-hosted app, detached from this terminal. Compatible with PowerShell 5.1/7.
$ErrorActionPreference = 'Stop'
$Port = 8006
$Root = $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Logs = Join-Path $Root 'logs'

if (-not (Test-Path $Python)) {
    & (Join-Path $Root 'setup.ps1')
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Python)) { throw 'Setup failed; server was not started.' }
}
& $Python -c 'import fastapi, uvicorn, sqlalchemy, apscheduler, pydantic_settings'
if ($LASTEXITCODE -ne 0) { throw 'Missing dependencies. Run .\setup.ps1 first.' }
New-Item -ItemType Directory -Path $Logs -Force | Out-Null

$Existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Existing) {
    try {
        $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 3
        if ($Health.ok -and $Health.app -eq 'JobHunt Finland') {
            Write-Host "JobHunt is already running at http://127.0.0.1:$Port/"
            exit 0
        }
    } catch {}
    throw "Port $Port is occupied. Verify the existing process before stopping it."
}

$Out = Join-Path $Logs 'uvicorn.log'
$Err = Join-Path $Logs 'uvicorn.err.log'
$Command = 'cmd.exe /d /s /c ""{0}" -m uvicorn src.main:app --host 127.0.0.1 --port {1} > "{2}" 2> "{3}""' -f $Python, $Port, $Out, $Err
$Process = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $Command
    CurrentDirectory = $Root
}
if ($Process.ReturnValue -ne 0) { throw "Server launch failed (CIM code $($Process.ReturnValue))." }

Write-Host 'Waiting for the dashboard. Jobs refresh in the background.'
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    Start-Sleep -Seconds 1
    try {
        $Health = Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2
        if ($Health.ok) {
            Write-Host "Dashboard ready: http://127.0.0.1:$Port/" -ForegroundColor Green
            exit 0
        }
    } catch {}
}
throw 'Server failed its startup health check. See logs/uvicorn.err.log.'
