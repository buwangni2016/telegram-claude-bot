#!/bin/bash
# ================================================
# setup_v3.sh - 全功能娱乐版部署脚本 (v3-full)
# 用法: bash scripts/setup_v3.sh <BOT_TOKEN>
# ================================================
set -e

VERSION="3.0.0"
PM2_NAME="telegram-remote"
WORKDIR="/home/vercel-sandbox"
REPO_DIR="$WORKDIR/telegram-claude-bot"
BOT_SCRIPT="$REPO_DIR/bot_v3.py"
CONFIG="$REPO_DIR/config/v3.json"
KEEPALIVE="$REPO_DIR/keepalive.sh"
TOKEN_FILE="$HOME/.bot_token"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo ""
echo "================================================"
echo "  Telegram Claude Bot v${VERSION} (v3-full)"
echo "================================================"
echo ""

BOT_TOKEN="${1:-}"
[ -z "$BOT_TOKEN" ] && [ -f "$TOKEN_FILE" ] && BOT_TOKEN=$(cat "$TOKEN_FILE") && warn "使用已保存的 Token"
[ -z "$BOT_TOKEN" ] && err "请提供 Token: bash scripts/setup_v3.sh <TOKEN>"
echo "$BOT_TOKEN" > "$TOKEN_FILE" && chmod 600 "$TOKEN_FILE"
ok "Token 已保存"

command -v python3 >/dev/null || err "Python3 未安装"
command -v pm2     >/dev/null || err "PM2 未安装"
command -v claude  >/dev/null || err "claude CLI 未安装"

# v3 额外依赖
python3 -c "import qrcode" 2>/dev/null || pip install qrcode Pillow -q
python3 -c "import requests" 2>/dev/null || pip install requests -q
ok "依赖检查通过 (含 qrcode / Pillow)"

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
echo "$BOT_INFO" | grep -q "ERROR" && err "Token 无效"
ok "Bot 验证: $BOT_INFO"

rm -f "$WORKDIR/telegram_remote.lock"
pm2 list 2>/dev/null | grep -q "$PM2_NAME" && pm2 delete "$PM2_NAME" >/dev/null 2>&1 && warn "已删除旧进程"

pm2 start "$BOT_SCRIPT" \
    --name "$PM2_NAME" \
    --interpreter python3 \
    --max-memory-restart 200M \
    --restart-delay 3000 \
    >/dev/null 2>&1
pm2 save >/dev/null 2>&1
ok "PM2 进程已启动: $PM2_NAME"

chmod +x "$KEEPALIVE"
bash "$KEEPALIVE" >/dev/null 2>&1
ok "保活脚本验证通过"

echo ""
echo "================================================"
echo "  v3-full 部署完成"
echo "================================================"
pm2 list
echo ""
echo -e "${GREEN}Bot:${NC} $BOT_INFO"
echo ""
echo "管理命令:"
echo "  pm2 logs $PM2_NAME"
echo "  pm2 restart $PM2_NAME"
echo ""
echo -e "${YELLOW}注意:${NC} 保活 Cron 任务请在 Claude 会话中执行:"
echo "  帮我续期保活任务，脚本路径 $KEEPALIVE，每5分钟一次"
echo ""
echo -e "${YELLOW}v3-full 特有功能:${NC}"
echo "  底部图形菜单 / 游戏大厅 / 天气/IP/二维码/翻译 / 网站监控 / 定时任务"
echo ""
