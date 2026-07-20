#!/usr/bin/env bash
# Stop the JobHunt Finland FastAPI server running on port 8006 on macOS/Linux.

PORT=8006

if command -v lsof >/dev/null 2>&1; then
    PID=$(lsof -Pi :"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
    if [ -n "$PID" ]; then
        kill "$PID"
        echo "Stopped server on port $PORT (PID $PID)."
        exit 0
    fi
fi

echo "No server found on port $PORT."
