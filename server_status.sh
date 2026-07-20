#!/usr/bin/env bash
# Check whether the JobHunt Finland FastAPI server is running on port 8006.

PORT=8006

if command -v lsof >/dev/null 2>&1; then
    PID=$(lsof -Pi :"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
    if [ -n "$PID" ]; then
        echo "Server is running on http://127.0.0.1:$PORT/ (PID $PID)"
        exit 0
    fi
fi

echo "Server is not running on port $PORT."
exit 1
