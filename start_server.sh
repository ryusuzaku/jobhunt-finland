#!/usr/bin/env bash
# Start the JobHunt Finland FastAPI server as a background process on macOS/Linux.
# Logs are written to logs/uvicorn.log and logs/uvicorn.err.log.

PORT=8006
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run one-time setup if the virtual environment is missing.
if [ ! -d "$ROOT/.venv" ]; then
    "$ROOT/setup.sh"
fi

mkdir -p "$ROOT/logs"

if command -v lsof >/dev/null 2>&1 && lsof -Pi :"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Server already running on port $PORT."
    exit 0
fi

echo "Starting uvicorn on port $PORT..."
nohup "$ROOT/.venv/bin/python" -m uvicorn src.main:app --host 127.0.0.1 --port "$PORT" --reload \
    > "$ROOT/logs/uvicorn.log" 2> "$ROOT/logs/uvicorn.err.log" &

sleep 3

if command -v lsof >/dev/null 2>&1 && lsof -Pi :"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Server started successfully on http://127.0.0.1:$PORT/"
else
    echo "Server may have failed to start. Check logs/uvicorn.err.log"
fi
