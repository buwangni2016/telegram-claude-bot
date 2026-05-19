#!/bin/bash
# ================================================
# Telegram Claude Bot 一键部署脚本
# 用法: bash setup.sh <BOT_TOKEN>
# 仓库: https://github.com/buwangni2016/telegram-claude-bot
# ================================================

set -e

REPO="https://github.com/buwangni2016/telegram-claude-bot"
RAW="https://raw.githubusercontent.com/buwangni2016/telegram-claude-bot/main"
WORKDIR="/home/vercel-sandbox"
PM2_NAME="telegram-remote"
BOT_SCRIPT="$WORKDIR/telegram_remote_control.py"
KEEPALIVE="$WORKDIR/keepalive.sh"
TOKEN_FILE="$HOME/.bot_token"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo "================================================"
echo "  Telegram Claude Bot 一键部署"
echo "================================================"
echo ""

# ── 1. Bot Token ──────────────────────────────────
BOT_TOKEN="${1:-}"
if [ -z "$BOT_TOKEN" ] && [ -f "$TOKEN_FILE" ]; then
    BOT_TOKEN=$(cat "$TOKEN_FILE")
    warn "使用已保存的 Token"
fi
[ -z "$BOT_TOKEN" ] && err "请提供 Bot Token: bash setup.sh <TOKEN>"
echo "$BOT_TOKEN" > "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
ok "Token 已保存到 $TOKEN_FILE"

# ── 2. 检查依赖 ────────────────────────────────────
command -v python3 >/dev/null 2>&1 || err "Python3 未安装"
command -v pm2     >/dev/null 2>&1 || err "PM2 未安装"
command -v claude  >/dev/null 2>&1 || err "claude CLI 未安装"
ok "依赖检查通过 (python3 / pm2 / claude)"

# ── 3. 拉取最新脚本 ────────────────────────────────
echo ""
echo "从 GitHub 拉取最新文件..."
curl -fsSL "$RAW/bot.py"          -o "$BOT_SCRIPT"
curl -fsSL "$RAW/keepalive.sh"    -o "$KEEPALIVE"
chmod +x "$BOT_SCRIPT" "$KEEPALIVE"
ok "文件已更新: bot.py / keepalive.sh"

# ── 4. 验证 Token ──────────────────────────────────
BOT_INFO=$(python3 -c "
import urllib.request, json
try:
    with urllib.request.urlopen('https://api.telegram.org/bot${BOT_TOKEN}/getMe', timeout=10) as r:
        d = json.load(r)
    b = d['result']
    print(f\"{b.get('first_name','')} @{b.get('username','')} id={b.get('id','')}\")
except Exception as e:
    print(f'ERROR:{e}')
" 2>/dev/null)
echo "$BOT_INFO" | grep -q "ERROR" && err "Bot Token 无效: $BOT_INFO"
ok "Bot 验证通过: $BOT_INFO"

# ── 5. 停止旧进程 ──────────────────────────────────
rm -f "$WORKDIR/telegram_remote.lock"
if pm2 list 2>/dev/null | grep -q "$PM2_NAME"; then
    pm2 delete "$PM2_NAME" >/dev/null 2>&1
    warn "已删除旧进程"
fi

# ── 6. PM2 启动 ────────────────────────────────────
pm2 start "$BOT_SCRIPT" \
    --name "$PM2_NAME" \
    --interpreter python3 \
    --max-memory-restart 200M \
    --restart-delay 3000 \
    >/dev/null 2>&1
pm2 save >/dev/null 2>&1
ok "PM2 进程已启动: $PM2_NAME"

# ── 7. 保活验证 ────────────────────────────────────
sleep 2
bash "$KEEPALIVE" >/dev/null 2>&1
ok "保活脚本验证通过"

# ── 完成 ───────────────────────────────────────────
echo ""
echo "================================================"
echo "  部署完成"
echo "================================================"
pm2 list
echo ""
echo -e "${GREEN}Bot:${NC}    $BOT_INFO"
echo -e "${GREEN}仓库:${NC}   $REPO"
echo ""
echo "管理命令:"
echo "  pm2 logs $PM2_NAME       # 查看日志"
echo "  pm2 restart $PM2_NAME    # 重启"
echo "  bash setup.sh            # 更新到最新版本"
echo ""
echo -e "${YELLOW}注意:${NC} 保活 Cron 任务需在 Claude 会话中创建（7天有效期）"
echo "  指令: 帮我续期 Telegram Bot 保活任务，脚本路径 $KEEPALIVE，每5分钟一次"
echo ""
