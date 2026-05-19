#!/usr/bin/env python3
"""
bot_v1.py - 极简内核版 (v1-simple)
功能: AI 智能对话 + /cmd 终端命令执行 + 多轮记忆
运行: BOT_CONFIG=config/v1.json python3 bot_v1.py
"""

import os
import sys
import time

# 指定配置文件
os.environ.setdefault("BOT_CONFIG",
    os.path.join(os.path.dirname(__file__), "config/v1.json"))

from modules.core import (
    TELEGRAM_BOT_TOKEN, executor, log, shell,
    send_message, ask_claude_async, build_prompt, ask_claude,
    load_history, save_history, clear_history,
    load_poll_state, save_poll_state, heartbeat,
    acquire_lock, release_lock, tg_api, load_json
)

if not TELEGRAM_BOT_TOKEN:
    print("错误: 未设置 Bot Token，请运行 setup_v1.sh <TOKEN>")
    sys.exit(1)

_cfg      = load_json(os.environ["BOT_CONFIG"], {})
ADMIN_IDS = set(_cfg.get("ADMIN_IDS", []))

BLOCKED_CMDS = [
    "rm -rf /", "dd if=/dev/zero", "mkfs", ":(){ :|:& };:",
    "> /dev/sda", "shutdown", "reboot", "halt",
]

# ===================== 命令执行 =====================
def execute_command(cmd):
    for kw in BLOCKED_CMDS:
        if kw.lower() in cmd.lower():
            return f"⛔ 高危命令已拦截: {kw}"
    try:
        import subprocess
        r   = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             timeout=30, cwd=os.environ.get("BOT_WORKDIR", "/home/vercel-sandbox"))
        out = r.stdout or r.stderr or "(无输出)"
        rc  = "✅ OK" if r.returncode == 0 else f"⚠️ rc={r.returncode}"
        return f"{rc}\n\n```\n{out}\n```"
    except Exception as e:
        return f"❌ {e}"

# ===================== 消息处理 =====================
def process_message(chat_id, username, msg_id, text):
    if text.startswith("/cmd"):
        if int(chat_id) not in ADMIN_IDS:
            send_message(chat_id, "⛔ /cmd 仅限管理员。", msg_id)
            return
        cmd = text[4:].strip()
        if not cmd:
            send_message(chat_id, "用法: /cmd <命令>", msg_id)
            return
        log(f"[CMD] [{username}] {cmd}")
        send_message(chat_id, f"⚙️ 执行: `{cmd}`", msg_id)
        send_message(chat_id, execute_command(cmd), msg_id)

    elif text == "/start":
        send_message(chat_id, (
            "🤖 Telegram Claude Bot v1-simple\n\n"
            "直接发消息 → Claude AI 智能回复（带多轮记忆）\n\n"
            "/cmd <命令> — 执行 Linux 终端命令（管理员）\n"
            "/clear      — 清除对话历史\n"
            "/help       — 使用说明"
        ), msg_id)

    elif text == "/help":
        h = load_history(chat_id)
        send_message(chat_id, (
            f"📖 使用说明 (v1-simple)\n\n"
            f"对话轮数: {len(h)//2} 轮\n\n"
            f"• 直接发消息 → Claude AI 回复\n"
            f"• /cmd <命令> → 执行终端命令（仅管理员）\n"
            f"• /clear → 清除对话历史\n\n"
            f"升级到 v2-secure 可获得权限管理+系统监控\n"
            f"升级到 v3-full 可获得图形菜单+游戏+工具箱"
        ), msg_id)

    elif text == "/clear":
        clear_history(chat_id)
        send_message(chat_id, "🧹 对话历史已清除。", msg_id)

    else:
        send_message(chat_id, "⏳ 思考中...", msg_id)
        executor.submit(ask_claude_async, chat_id, msg_id, username, text)

# ===================== 主循环 =====================
def process_updates():
    state  = load_poll_state()
    params = {"limit": 20}
    if state["last_update_id"]:
        params["offset"] = state["last_update_id"] + 1

    updates = tg_api("getUpdates", params).get("result", [])
    for update in updates:
        uid = update["update_id"]
        state["last_update_id"] = max(state.get("last_update_id", 0), uid)
        msg      = update.get("message", {})
        text     = msg.get("text", "")
        chat_id  = msg.get("chat", {}).get("id")
        username = msg.get("from", {}).get("first_name", "用户")
        msg_id   = msg.get("message_id")
        if not chat_id or not text:
            continue
        try:
            process_message(chat_id, username, msg_id, text)
        except Exception as e:
            log(f"process error: {e}")

    save_poll_state(state)
    heartbeat(state)

def main():
    if not acquire_lock():
        sys.exit(0)
    log("Bot v1-simple started")
    log(f"Admins: {ADMIN_IDS}")
    try:
        while True:
            try:
                process_updates()
            except Exception as e:
                log(f"poll error: {e}")
            time.sleep(2)
    except KeyboardInterrupt:
        log("stopped")
    finally:
        executor.shutdown(wait=False)
        release_lock()

if __name__ == "__main__":
    main()
