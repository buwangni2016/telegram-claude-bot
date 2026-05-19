"""
core.py - 核心通用模块 (所有版本共享)
包含: TG API 封装 / 消息发送 / 对话历史 / Claude 调用 / 状态持久化 / 心跳
"""

import json
import os
import subprocess
import time
import threading
import urllib.request
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ===================== 配置加载 =====================
WORKDIR      = os.environ.get("BOT_WORKDIR", "/home/vercel-sandbox")
_CONFIG_PATH = os.environ.get("BOT_CONFIG", os.path.join(WORKDIR, "telegram-claude-bot/config/v1.json"))

def load_config(path=None):
    path = path or _CONFIG_PATH
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def _load_token():
    t = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if t:
        return t
    cfg = os.path.expanduser("~/.bot_token")
    if os.path.exists(cfg):
        return open(cfg).read().strip()
    return ""

# ===================== 全局常量 (可被 config 覆盖) =====================
_cfg               = load_config()
TELEGRAM_BOT_TOKEN = _load_token()
POLL_INTERVAL      = _cfg.get("POLL_INTERVAL", 2)
CLAUDE_TIMEOUT     = _cfg.get("CLAUDE_TIMEOUT", 120)
HEARTBEAT_INTERVAL = _cfg.get("HEARTBEAT_INTERVAL", 300)
MAX_AI_WORKERS     = _cfg.get("MAX_AI_WORKERS", 3)
MAX_HISTORY        = _cfg.get("MAX_HISTORY", 20)
HISTORY_DIR        = os.path.join(WORKDIR, "chat_history")
STATE_FILE         = os.path.join(WORKDIR, "telegram_remote_state.json")
LOCK_FILE          = os.path.join(WORKDIR, "telegram_remote.lock")

os.makedirs(HISTORY_DIR, exist_ok=True)

executor   = ThreadPoolExecutor(max_workers=MAX_AI_WORKERS)
state_lock = threading.Lock()
_last_heartbeat = time.time()

# ===================== 工具函数 =====================
def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def shell(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, cwd=WORKDIR)
        return (r.stdout or r.stderr or "(无输出)").strip()
    except subprocess.TimeoutExpired:
        return "超时"
    except Exception as e:
        return f"错误: {e}"

# ===================== Telegram API =====================
def tg_api(method, data=None, files=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    if files is None:
        body = json.dumps(data or {}).encode()
        req  = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
    else:
        boundary = "TGBoundary"
        parts = []
        for key, val in (data or {}).items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{val}'
                .encode()
            )
        for fname, fbytes in files.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{fname}"\r\nContent-Type: image/png\r\n\r\n'
                .encode() + fbytes
            )
        body = b"\r\n".join(parts) + f"\r\n--{boundary}--\r\n".encode()
        req  = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)

def send_message(chat_id, text, reply_to=None, keyboard=None):
    chunks = paginate(text)
    for i, chunk in enumerate(chunks):
        data = {"chat_id": chat_id, "text": chunk}
        if reply_to and i == 0:
            data["reply_to_message_id"] = reply_to
        if keyboard and i == len(chunks) - 1:
            data["reply_markup"] = keyboard
        try:
            tg_api("sendMessage", data)
        except Exception as e:
            log(f"send failed: {e}")

def paginate(text, limit=4000):
    if len(text) <= limit:
        return [text]
    pages = []
    while text:
        if len(text) <= limit:
            pages.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        pages.append(text[:cut])
        text = text[cut:].lstrip("\n")
    total = len(pages)
    return [f"[{i+1}/{total}]\n{p}" for i, p in enumerate(pages)]

def answer_callback(callback_id):
    try:
        tg_api("answerCallbackQuery", {"callback_query_id": callback_id})
    except Exception:
        pass

# ===================== 对话历史 =====================
def history_path(chat_id):
    return os.path.join(HISTORY_DIR, f"{chat_id}.json")

def load_history(chat_id):
    return load_json(history_path(chat_id), [])

def save_history(chat_id, history):
    save_json(history_path(chat_id), history[-MAX_HISTORY:])

def clear_history(chat_id):
    p = history_path(chat_id)
    if os.path.exists(p):
        os.remove(p)

def build_prompt(chat_id, new_message, persona=None):
    history = load_history(chat_id)
    lines   = []
    if persona:
        lines.append(f"你现在扮演以下角色，请保持角色一致回复：{persona}\n")
    if history:
        lines.append("以下是我们之前的对话（请基于此继续）：\n")
        for e in history:
            role = "用户" if e["role"] == "user" else "Claude"
            lines.append(f"[{role}]: {e['content']}")
        lines.append("")
    lines.append(f"[用户]: {new_message}")
    return "\n".join(lines)

# ===================== Claude 调用 =====================
def ask_claude(prompt, timeout=None):
    timeout = timeout or CLAUDE_TIMEOUT
    try:
        r = subprocess.run(["claude", "--print", prompt],
                           capture_output=True, text=True,
                           timeout=timeout, cwd=WORKDIR)
        return r.stdout.strip() or r.stderr.strip() or "（无返回，请重试）"
    except subprocess.TimeoutExpired:
        return f"处理超时（{timeout}秒），请简化后重试。"
    except FileNotFoundError:
        return "claude CLI 未找到。"
    except Exception as e:
        return f"出错: {e}"

def ask_claude_async(chat_id, msg_id, username, text):
    log(f"[AI] [{username}] {text[:60]}")
    prompt  = build_prompt(chat_id, text)
    reply   = ask_claude(prompt)
    history = load_history(chat_id)
    history.append({"role": "user",      "content": text})
    history.append({"role": "assistant", "content": reply})
    save_history(chat_id, history)
    send_message(chat_id, reply, msg_id)
    log(f"[AI] done ({len(reply)}chars) history:{len(history)//2}rounds")

# ===================== 状态持久化 =====================
def load_poll_state():
    return load_json(STATE_FILE, {"last_update_id": 0})

def save_poll_state(state):
    with state_lock:
        save_json(STATE_FILE, state)

def heartbeat(state):
    global _last_heartbeat
    now = time.time()
    if now - _last_heartbeat > HEARTBEAT_INTERVAL:
        log(f"heartbeat offset={state.get('last_update_id', 0)}")
        _last_heartbeat = now

# ===================== 锁文件管理 =====================
def acquire_lock():
    if os.path.exists(LOCK_FILE):
        if time.time() - os.path.getmtime(LOCK_FILE) > 90:
            os.remove(LOCK_FILE)
        else:
            log("already running, exit")
            return False
    open(LOCK_FILE, "w").close()
    return True

def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)
