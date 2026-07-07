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
# --reload is omitted so the background PID matches the listening port and stop scripts work reliably.
nohup "$ROOT/.venv/bin/python" -m uvicorn src.main:app --host 127.0.0.1 --port "$PORT" \
    > "$ROOT/logs/uvicorn.log" 2> "$ROOT/logs/uvicorn.err.log" &

# Uvicorn binds the port after the lifespan startup fetch completes, which can take ~30-60s.
echo "Waiting for the first fetch to finish and the port to come up..."
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    if command -v lsof >/dev/null 2>&1 && lsof -Pi :"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "Server started successfully on http://127.0.0.1:$PORT/"
        exit 0
    fi
done

echo "Server did not bind to port $PORT within ${TIMEOUT}s. It may still be starting; check logs/uvicorn.err.log"
