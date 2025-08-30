#!/bin/zsh
cd /Users/s.w.roseburgh/n8n-docker
mkdir -p "$HOME/Library/Logs/Emerge"
/usr/bin/printenv >/dev/null

set -a
[ -f .env ] && . ./.env
set +a

if [ -n "$BOT_TOKEN" ]; then
  /usr/bin/curl -s "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" -d url= >/dev/null
fi

exec /Users/s.w.roseburgh/n8n-docker/venv311/bin/python -u /Users/s.w.roseburgh/n8n-docker/emerge_bot.py
