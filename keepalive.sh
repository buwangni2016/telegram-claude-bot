#!/bin/bash
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
LOG_FILE="/home/vercel-sandbox/keepalive.log"

echo "[$TIMESTAMP] 💓 Keepalive heartbeat" >> "$LOG_FILE"

PM2_ONLINE=$(pm2 list | grep -c "online" || true)
echo "[$TIMESTAMP] PM2进程数: $PM2_ONLINE" >> "$LOG_FILE"

if ! pm2 list | grep -q "telegram-remote.*online"; then
    echo "[$TIMESTAMP] ⚠️ telegram-remote 未运行，尝试重启" >> "$LOG_FILE"
    pm2 restart telegram-remote 2>&1 >> "$LOG_FILE"
fi

# 保留最近500行日志
if [ -f "$LOG_FILE" ]; then
    tail -500 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
fi

echo "Keepalive: $TIMESTAMP"
