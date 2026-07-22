#!/usr/bin/env bash
# JobHunt Finland watchdog (macOS/Linux).
# Checks whether the dashboard port is listening; restarts the server if not.
#
# Install via cron (every 5 minutes + once at boot):
#   crontab -e
#   */5 * * * * /path/to/jobhunt/watchdog.sh
#   @reboot /path/to/jobhunt/watchdog.sh

PORT=8006
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$ROOT/logs/watchdog.log"

mkdir -p "$ROOT/logs"

if command -v lsof >/dev/null 2>&1 && lsof -Pi :"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') Port $PORT not listening; restarting server..." >> "$LOG"
"$ROOT/start_server.sh" >> "$LOG" 2>&1
