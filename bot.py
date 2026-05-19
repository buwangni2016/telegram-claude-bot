#!/usr/bin/env python3
"""
Telegram 远程控制 Bot
- /cmd <命令>  → 直接执行 Linux 命令
- 普通消息     → 调用 claude --print 异步处理（带完整工具能力）
"""

import json
import os
import subprocess
import time
import threading
import urllib.request
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ========== 配置 ==========
def _load_token():
    """优先读环境变量，其次读 ~/.bot_token 文件"""
    t = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if t:
        return t
    cfg = os.path.expanduser("~/.bot_token")
    if os.path.exists(cfg):
        return open(cfg).read().strip()
    return ""

TELEGRAM_BOT_TOKEN = _load_token()
if not TELEGRAM_BOT_TOKEN:
    print("错误: 未设置 TELEGRAM_BOT_TOKEN，请运行 setup.sh <TOKEN> 或设置环境变量")
    exit(1)

STATE_FILE         = "/home/vercel-sandbox/telegram_remote_state.json"
LOCK_FILE          = "/home/vercel-sandbox/telegram_remote.lock"
HISTORY_DIR        = "/home/vercel-sandbox/chat_history"
POLL_INTERVAL      = 2
MAX_OUTPUT_LEN     = 4000
CLAUDE_TIMEOUT     = 120
HEARTBEAT_INTERVAL = 300
MAX_AI_WORKERS     = 3
MAX_HISTORY        = 20   # 每个用户保留最近20条消息
# ==========================

last_heartbeat = time.time()
executor = ThreadPoolExecutor(max_workers=MAX_AI_WORKERS)
state_lock = threading.Lock()
os.makedirs(HISTORY_DIR, exist_ok=True)


def history_path(chat_id):
    return os.path.join(HISTORY_DIR, f"{chat_id}.json")


def load_history(chat_id):
    p = history_path(chat_id)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(chat_id, history):
    with open(history_path(chat_id), "w", encoding="utf-8") as f:
        json.dump(history[-MAX_HISTORY:], f, ensure_ascii=False, indent=2)


def build_prompt(chat_id, new_message):
    """将历史记录拼入 prompt，让 Claude 具备多轮记忆"""
    history = load_history(chat_id)
    if not history:
        return new_message

    lines = ["以下是我们之前的对话记录（请基于此继续回复）：", ""]
    for entry in history:
        role = "用户" if entry["role"] == "user" else "Claude"
        lines.append(f"[{role}]: {entry['content']}")
    lines.append("")
    lines.append(f"[用户]: {new_message}")
    return "\n".join(lines)


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_update_id": 0}


def save_state(state):
    with state_lock:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)


def tg_api(method, data=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def send_message(chat_id, text, reply_to=None):
    if len(text) > MAX_OUTPUT_LEN:
        text = text[:MAX_OUTPUT_LEN - 80] + "\n\n...(已截断)"
    data = {"chat_id": chat_id, "text": text}
    if reply_to:
        data["reply_to_message_id"] = reply_to
    try:
        return tg_api("sendMessage", data)
    except Exception as e:
        log(f"发送失败: {e}")


def execute_command(cmd):
    blacklist = ["rm -rf /", "dd if=/dev/zero", "mkfs", ":(){ :|:& };:", "> /dev/sda"]
    for kw in blacklist:
        if kw in cmd.lower():
            return f"❌ 拒绝高危命令: {kw}"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=30, cwd="/home/vercel-sandbox")
        out = r.stdout or r.stderr or "(无输出)"
        status = "✅" if r.returncode == 0 else f"⚠️ 返回码:{r.returncode}"
        return f"{status}\n\n```\n{out}\n```"
    except subprocess.TimeoutExpired:
        return "⏱️ 执行超时（30秒）"
    except Exception as e:
        return f"❌ 错误: {e}"


def ask_claude_async(chat_id, msg_id, username, text):
    log(f"[AI] [{username}] {text[:60]}")
    try:
        prompt = build_prompt(chat_id, text)
        result = subprocess.run(
            ["claude", "--print", prompt],
            capture_output=True, text=True,
            timeout=CLAUDE_TIMEOUT, cwd="/home/vercel-sandbox",
        )
        reply = result.stdout.strip() or result.stderr.strip() or "（未返回内容，请重试）"
    except subprocess.TimeoutExpired:
        reply = f"⏱️ 处理超时（{CLAUDE_TIMEOUT}秒），请简化后重试。"
    except FileNotFoundError:
        reply = "❌ claude CLI 未找到。"
    except Exception as e:
        reply = f"❌ 出错: {e}"
        log(f"[AI] 异常: {e}")

    # 保存本轮对话到历史
    history = load_history(chat_id)
    history.append({"role": "user",      "content": text})
    history.append({"role": "assistant", "content": reply})
    save_history(chat_id, history)

    send_message(chat_id, reply, msg_id)
    log(f"[AI] 完成 ({len(reply)}字) 历史:{len(history)//2}轮")


def process_updates():
    global last_heartbeat
    state = load_state()
    offset = state["last_update_id"] + 1 if state["last_update_id"] else None
    params = {"limit": 10}
    if offset:
        params["offset"] = offset

    result = tg_api("getUpdates", params)
    updates = result.get("result", [])

    for update in updates:
        update_id = update["update_id"]
        msg      = update.get("message", {})
        text     = msg.get("text", "")
        chat_id  = msg.get("chat", {}).get("id")
        username = msg.get("from", {}).get("first_name", "用户")
        msg_id   = msg.get("message_id")

        if not text or not chat_id:
            state["last_update_id"] = max(state.get("last_update_id", 0), update_id)
            continue

        if text.startswith("/cmd "):
            cmd = text[5:].strip()
            if not cmd:
                send_message(chat_id, "❌ 用法: /cmd <命令>", msg_id)
            else:
                log(f"[CMD] [{username}] {cmd}")
                send_message(chat_id, f"⚙️ 执行: `{cmd}`", msg_id)
                send_message(chat_id, execute_command(cmd), msg_id)

        elif text == "/start":
            send_message(chat_id, (
                "🤖 Claude 智能控制 Bot\n\n"
                "直接发消息，Claude 实时处理：\n"
                "• 聊天问答、写作、分析\n"
                "• 读写文件、查系统、调 API\n\n"
                "/cmd <命令> — 执行 Linux 命令\n"
                "/status     — 系统状态\n"
                "/help       — 使用说明"
            ), msg_id)

        elif text == "/status":
            send_message(chat_id, (
                f"📊 系统状态\n\n"
                f"⏰ {subprocess.getoutput('uptime')}\n\n"
                f"💾 {subprocess.getoutput('free -h | grep Mem')}\n\n"
                f"💿 {subprocess.getoutput('df -h / | tail -1')}\n\n"
                f"🔄 AI工作线程: {executor._work_queue.qsize()} 排队"
            ), msg_id)

        elif text == "/clear":
            p = history_path(chat_id)
            if os.path.exists(p):
                os.remove(p)
            send_message(chat_id, "🧹 对话历史已清除，开始新话题。", msg_id)
            log(f"[CLEAR] [{username}] 清除历史")

        elif text == "/help":
            history = load_history(chat_id)
            send_message(chat_id, (
                "📖 使用说明\n\n"
                "💬 直接发消息 → Claude 异步处理（带记忆）\n"
                f"当前对话轮数: {len(history)//2} 轮 / 最多 {MAX_HISTORY//2} 轮\n\n"
                "示例:\n"
                "  帮我查看系统进程\n"
                "  读取某个文件\n"
                "  今天星期几\n\n"
                "🖥️ /cmd <命令> → 立即执行\n"
                "  /cmd ls -lah\n"
                "  /cmd df -h\n"
                "  /cmd ps aux | head -10\n\n"
                "/clear — 清除对话历史，开始新话题\n"
                "⚠️ 高危命令自动拦截"
            ), msg_id)

        else:
            send_message(chat_id, "🤔 处理中...", msg_id)
            executor.submit(ask_claude_async, chat_id, msg_id, username, text)

        state["last_update_id"] = max(state.get("last_update_id", 0), update_id)

    save_state(state)

    now = time.time()
    if now - last_heartbeat > HEARTBEAT_INTERVAL:
        log(f"💓 心跳 offset={state.get('last_update_id', 0)}")
        last_heartbeat = now


def cleanup_lock():
    if os.path.exists(LOCK_FILE):
        age = time.time() - os.path.getmtime(LOCK_FILE)
        if age > 90:
            os.remove(LOCK_FILE)
            log("🧹 清理残留锁文件")
            return True
        else:
            log("❌ 已有实例运行，退出")
            return False
    return True


def main():
    if not cleanup_lock():
        exit(0)
    open(LOCK_FILE, "w").close()
    log("🚀 Bot 启动")
    log(f"⏱️  轮询:{POLL_INTERVAL}s  Claude超时:{CLAUDE_TIMEOUT}s  AI并发:{MAX_AI_WORKERS}")
    try:
        while True:
            try:
                process_updates()
            except Exception as e:
                log(f"⚠️ 轮询错误: {e}")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        log("停止")
    finally:
        executor.shutdown(wait=False)
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)


if __name__ == "__main__":
    main()
