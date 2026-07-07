#!/usr/bin/env bash
# One-time setup for JobHunt Finland on macOS/Linux.
# Creates the virtual environment, installs dependencies, seeds .env, and creates data/log directories.

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PYTHON="${PYTHON:-python3}"

echo "JobHunt Finland setup"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Error: $PYTHON is not installed or not on PATH. Please install Python 3.11+ and try again."
    exit 1
fi

if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment in $VENV..."
    "$PYTHON" -m venv "$VENV"
else
    echo "Virtual environment already exists."
fi

echo "Upgrading pip..."
"$VENV/bin/pip" install --upgrade pip

echo "Installing dependencies from requirements.txt..."
"$VENV/bin/pip" install -r "$ROOT/requirements.txt"

if [ ! -f "$ROOT/.env" ]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo "Created .env from .env.example. Edit it to add email/webhook settings if you want alerts."
fi

mkdir -p "$ROOT/data" "$ROOT/logs"

echo "Setup complete. Run ./start_server.sh to start the dashboard."
