#!/bin/bash
set -a
source /Users/s.w.roseburgh/n8n-docker/.env
set +a

PYTHONWARNINGS="ignore::UserWarning:apscheduler" \
nohup /Users/s.w.roseburgh/n8n-docker/venv311/bin/python -u \
  /Users/s.w.roseburgh/n8n-docker/emerge_bot.py \
  >/tmp/emerge_bot.out 2>&1 &

echo "🚀 Bot started. Logs: tail -f /tmp/emerge_bot.out"
