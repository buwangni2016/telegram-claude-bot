#!/usr/bin/env python3
"""
bot_v2.py - 安全增强版 (v2-secure)
功能: v1 全部 + 权限分级 + 审计日志 + 系统监控 + 后台告警
运行: BOT_CONFIG=config/v2.json python3 bot_v2.py
"""

import os
import sys
import time

os.environ.setdefault("BOT_CONFIG",
    os.path.join(os.path.dirname(__file__), "config/v2.json"))

from modules.core import (
    TELEGRAM_BOT_TOKEN, executor, log, shell,
    send_message, ask_claude_async, load_history, clear_history,
    load_poll_state, save_poll_state, heartbeat,
    acquire_lock, release_lock, tg_api, load_json
)
from modules.security import (
    is_admin, is_blacklisted, audit, execute_command, get_audit_tail
)
from modules.monitoring import (
    get_status_text, get_mem_text, get_disk_text, get_net_text,
    start_background_threads
)

if not TELEGRAM_BOT_TOKEN:
    print("错误: 未设置 Bot Token，请运行 setup_v2.sh <TOKEN>")
    sys.exit(1)

# ===================== 内联状态面板键盘 =====================
KB_STATUS = {
    "inline_keyboard": [
        [{"text": "📊 状态", "callback_data": "cb_status"},
         {"text": "🧠 内存", "callback_data": "cb_mem"}],
        [{"text": "💿 磁盘", "callback_data": "cb_disk"},
         {"text": "🌐 网络", "callback_data": "cb_net"}],
    ]
}

# ===================== 消息处理 =====================
def process_message(chat_id, username, msg_id, text):
    if is_blacklisted(chat_id):
        send_message(chat_id, "⛔ 你已被限制使用此机器人。")
        return
    audit(chat_id, "MSG", text[:100])

    if text.startswith("/cmd"):
        if not is_admin(chat_id):
            send_message(chat_id, "⛔ /cmd 仅限管理员。", msg_id)
            return
        cmd = text[4:].strip()
        if not cmd:
            send_message(chat_id, "用法: /cmd <命令>", msg_id)
            return
        log(f"[CMD] [{username}] {cmd}")
        send_message(chat_id, f"⚙️ 执行: `{cmd}`", msg_id)
        send_message(chat_id, execute_command(cmd, chat_id), msg_id)

    elif text == "/status":
        send_message(chat_id, get_status_text(executor._work_queue.qsize()), msg_id, keyboard=KB_STATUS)
    elif text == "/mem":
        send_message(chat_id, get_mem_text(), msg_id)
    elif text == "/disk":
        send_message(chat_id, get_disk_text(), msg_id)
    elif text == "/net":
        send_message(chat_id, get_net_text(), msg_id)

    elif text in ("/audit", "/log"):
        if not is_admin(chat_id):
            send_message(chat_id, "⛔ 仅管理员可查看审计日志", msg_id)
            return
        send_message(chat_id, f"📋 最近30条审计日志:\n\n```\n{get_audit_tail(30)}\n```", msg_id)

    elif text == "/start":
        send_message(chat_id, (
            "🤖 Telegram Claude Bot v2-secure\n\n"
            "AI 对话: 直接发消息\n\n"
            "系统监控:\n"
            "/status  /mem  /disk  /net\n\n"
            "/cmd <命令> — 执行命令（管理员）\n"
            "/audit     — 审计日志（管理员）\n"
            "/clear     — 清除对话历史\n"
            "/help      — 使用说明"
        ), msg_id, keyboard=KB_STATUS)

    elif text == "/help":
        h = load_history(chat_id)
        admin_tip = "\n\n🔑 管理员: /cmd /audit" if is_admin(chat_id) else ""
        send_message(chat_id, (
            f"📖 使用说明 (v2-secure)\n\n"
            f"对话轮数: {len(h)//2} 轮\n\n"
            f"监控: /status  /mem  /disk  /net\n"
            f"AI: 直接发消息{admin_tip}"
        ), msg_id)

    elif text == "/clear":
        clear_history(chat_id)
        send_message(chat_id, "🧹 对话历史已清除。", msg_id)

    else:
        send_message(chat_id, "⏳ 思考中...", msg_id)
        executor.submit(ask_claude_async, chat_id, msg_id, username, text)


def process_callback(callback):
    cid  = callback["message"]["chat"]["id"]
    mid  = callback["message"]["message_id"]
    data = callback.get("data", "")
    try:
        tg_api("answerCallbackQuery", {"callback_query_id": callback["id"]})
    except Exception:
        pass
    dispatch = {
        "cb_status": lambda: send_message(cid, get_status_text(), mid),
        "cb_mem":    lambda: send_message(cid, get_mem_text(),    mid),
        "cb_disk":   lambda: send_message(cid, get_disk_text(),   mid),
        "cb_net":    lambda: send_message(cid, get_net_text(),    mid),
    }
    if data in dispatch:
        dispatch[data]()

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

        if "callback_query" in update:
            try:
                process_callback(update["callback_query"])
            except Exception as e:
                log(f"callback error: {e}")
            continue

        msg       = update.get("message", {})
        text      = msg.get("text", "")
        chat_id   = msg.get("chat", {}).get("id")
        username  = msg.get("from", {}).get("first_name", "用户")
        msg_id    = msg.get("message_id")
        chat_type = msg.get("chat", {}).get("type", "private")

        if not chat_id:
            continue
        if chat_type in ("group", "supergroup") and text and text.startswith("/cmd"):
            if not is_admin(chat_id):
                tg_api("sendMessage", {"chat_id": chat_id,
                    "text": "⛔ 群内禁止执行服务器命令。", "reply_to_message_id": msg_id})
                continue
        for member in msg.get("new_chat_members", []):
            tg_api("sendMessage", {"chat_id": chat_id,
                "text": f"👋 欢迎 {member.get('first_name','新朋友')} 加入！发送 /help 查看功能。"})

        if not text:
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
    log("Bot v2-secure started")
    start_background_threads()
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
