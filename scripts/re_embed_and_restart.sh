#!/bin/bash
# Wait for re-embed to finish, then restart dashboard backend

LOG="/tmp/re-embed.log"
PID=$(pgrep -f "python3 scripts/re_embed.py")

if [ -z "$PID" ]; then
    echo "re-embed process not found, may have already finished"
else
    echo "Waiting for re-embed (PID $PID) to finish..."
    tail -f "$LOG" --pid=$PID 2>/dev/null | grep --line-buffered "re-embed INFO" &
    wait $PID
    echo ""
    echo "Re-embed process finished."
fi

# Check if it completed successfully
if grep -q "Done! All.*records re-embedded" "$LOG"; then
    echo "Re-embedding succeeded. Restarting dashboard backend..."
    pkill -f "uvicorn dashboard.backend.main" 2>/dev/null
    sleep 2
    cd /home/asa/umbra
    HSA_OVERRIDE_GFX_VERSION=10.3.0 nohup /home/asa/umbra/.venv/bin/python3 -m uvicorn dashboard.backend.main:app --host 0.0.0.0 --port 8081 --log-level warning > /tmp/dashboard-restart.log 2>&1 &
    sleep 3
    echo "Dashboard backend restarted (PID $!)"
else
    echo "Re-embedding may not have completed successfully. Check $LOG"
    tail -5 "$LOG"
fi
