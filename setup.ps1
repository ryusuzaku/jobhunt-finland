# One-time setup for JobHunt Finland on Windows.
# Creates the virtual environment, installs dependencies, seeds .env, and creates data/log directories.

$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Venv = Join-Path $Root ".venv"
$Python = "python"

Write-Host "JobHunt Finland setup" -ForegroundColor Cyan

# Verify Python is available
& $Python --version | Out-Null
if (-not $?) {
    Write-Error "Python is not installed or not on PATH. Please install Python 3.11+ and try again."
    exit 1
}

# Create virtual environment if missing
if (-not (Test-Path $Venv)) {
    Write-Host "Creating virtual environment in $Venv..." -ForegroundColor Green
    & $Python -m venv $Venv
} else {
    Write-Host "Virtual environment already exists." -ForegroundColor Yellow
}

$Pip = Join-Path $Venv "Scripts\pip.exe"

Write-Host "Upgrading pip..." -ForegroundColor Green
& $Pip install --upgrade pip

Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Green
& $Pip install -r (Join-Path $Root "requirements.txt")

# Seed .env from example if the user has not created one
if (-not (Test-Path (Join-Path $Root ".env"))) {
    Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env")
    Write-Host "Created .env from .env.example. Edit it to add email/webhook settings if you want alerts." -ForegroundColor Cyan
}

# Ensure runtime directories exist
@("data", "logs") | ForEach-Object {
    $Dir = Join-Path $Root $_
    if (-not (Test-Path $Dir)) {
        New-Item -ItemType Directory -Path $Dir -Force | Out-Null
    }
}

Write-Host "Setup complete. Run .\start_server.ps1 to start the dashboard." -ForegroundColor Green
