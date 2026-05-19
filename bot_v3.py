#!/usr/bin/env python3
"""
Telegram Claude Bot v3.1.0 - 全面优化版
改进点:
  1. 长轮询 (getUpdates timeout=30)，替代 2s 定时轮询
  2. 状态机持久化 (user_states / game_states 写入文件)
  3. 配置文件驱动 (读取 config/v3.json，不硬编码)
  4. sendChatAction typing 指示器
  5. /cmd 正则黑名单，防绕过
  6. 对话历史按 token 数截断
  7. 错误回复友好化（用户/系统分层）
"""

import json, os, io, re, subprocess, time, threading, hashlib, random
import urllib.request, urllib.parse, urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ===================== 配置加载 =====================
_REPO_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "telegram-claude-bot")
_CFG_FILE   = os.path.join(_REPO_DIR, "config", "v3.json")

def _load_cfg():
    if os.path.exists(_CFG_FILE):
        with open(_CFG_FILE) as f:
            return json.load(f)
    return {}

_cfg = _load_cfg()

def _load_token():
    t = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if t:
        return t
    p = os.path.expanduser("~/.bot_token")
    return open(p).read().strip() if os.path.exists(p) else ""

TELEGRAM_BOT_TOKEN  = _load_token()
ADMIN_IDS           = set(_cfg.get("ADMIN_IDS", [7499029810]))
WORKDIR             = "/home/vercel-sandbox"
STATE_FILE          = f"{WORKDIR}/telegram_remote_state.json"
LOCK_FILE           = f"{WORKDIR}/telegram_remote.lock"
HISTORY_DIR         = f"{WORKDIR}/chat_history"
AUDIT_LOG           = f"{WORKDIR}/audit.log"
BLACKLIST_FILE      = f"{WORKDIR}/blacklist.json"
MONITOR_FILE        = f"{WORKDIR}/site_monitor.json"
CRON_FILE           = f"{WORKDIR}/user_crons.json"
UI_STATE_FILE       = f"{WORKDIR}/ui_states.json"   # 状态机持久化
GAME_STATE_FILE     = f"{WORKDIR}/game_states.json"  # 游戏状态持久化

LONG_POLL_TIMEOUT   = _cfg.get("LONG_POLL_TIMEOUT", 30)   # 长轮询等待秒数
CLAUDE_TIMEOUT      = _cfg.get("CLAUDE_TIMEOUT", 120)
HEARTBEAT_INTERVAL  = _cfg.get("HEARTBEAT_INTERVAL", 300)
MAX_AI_WORKERS      = _cfg.get("MAX_AI_WORKERS", 3)
MAX_HISTORY_TOKENS  = _cfg.get("MAX_HISTORY_TOKENS", 3000) # token 数上限
MEM_ALERT_PCT       = _cfg.get("MEM_ALERT_PCT", 85)
DISK_ALERT_PCT      = _cfg.get("DISK_ALERT_PCT", 85)
MONITOR_INTERVAL    = _cfg.get("MONITOR_INTERVAL", 60)

os.makedirs(HISTORY_DIR, exist_ok=True)

if not TELEGRAM_BOT_TOKEN:
    print("错误: 未设置 Token")
    exit(1)

executor       = ThreadPoolExecutor(max_workers=MAX_AI_WORKERS)
state_lock     = threading.Lock()
alert_sent     = {}
last_heartbeat = time.time()

# ===================== 键盘布局 =====================
REPLY_KEYBOARD = {
    "keyboard": [
        ["📊 系统监控", "🤖 AI 对话"],
        ["🛠️ 工具箱",  "🎮 游戏"],
        ["⚙️ 管理面板", "❓ 帮助"],
    ],
    "resize_keyboard": True,
    "persistent": True,
}
REPLY_BUTTON_MAP = {
    "📊 系统监控": "§menu_monitor",
    "🤖 AI 对话":  "§menu_ai",
    "🛠️ 工具箱":  "§menu_tools",
    "🎮 游戏":     "§menu_games",
    "⚙️ 管理面板": "§menu_admin",
    "❓ 帮助":     "§help",
}
KB_MONITOR = {"inline_keyboard": [
    [{"text": "📊 状态总览", "callback_data": "§status"},
     {"text": "🧠 内存",    "callback_data": "§mem"}],
    [{"text": "💿 磁盘",    "callback_data": "§disk"},
     {"text": "🌐 网络",    "callback_data": "§net"}],
    [{"text": "↩️ 返回",    "callback_data": "§home"}],
]}
KB_AI = {"inline_keyboard": [
    [{"text": "💬 智能对话",  "callback_data": "§ai_chat"},
     {"text": "🔍 代码分析", "callback_data": "§ai_code"}],
    [{"text": "🌐 翻译",      "callback_data": "§ai_tr"},
     {"text": "🎭 角色扮演", "callback_data": "§ai_talk"}],
    [{"text": "🧹 清除历史", "callback_data": "§clear"},
     {"text": "↩️ 返回",     "callback_data": "§home"}],
]}
KB_TOOLS = {"inline_keyboard": [
    [{"text": "🌤️ 天气",  "callback_data": "§weather"},
     {"text": "🔍 IP查询", "callback_data": "§ip"}],
    [{"text": "📷 二维码", "callback_data": "§qr"},
     {"text": "🌐 翻译",   "callback_data": "§ai_tr"}],
    [{"text": "↩️ 返回",   "callback_data": "§home"}],
]}
KB_GAMES = {"inline_keyboard": [
    [{"text": "🔢 猜数字（开始）", "callback_data": "§game_num_new"}],
    [{"text": "✊ 石头",  "callback_data": "§rps_石头"},
     {"text": "✌️ 剪刀", "callback_data": "§rps_剪刀"},
     {"text": "🖐️ 布",   "callback_data": "§rps_布"}],
    [{"text": "🎋 今日运势", "callback_data": "§fortune"}],
    [{"text": "↩️ 返回",    "callback_data": "§home"}],
]}
KB_ADMIN = {"inline_keyboard": [
    [{"text": "💻 执行命令",     "callback_data": "§cmd_input"},
     {"text": "📋 审计日志",    "callback_data": "§audit"}],
    [{"text": "⏰ 定时任务列表", "callback_data": "§cron_list"},
     {"text": "📡 监控站点",    "callback_data": "§monitor_list"}],
    [{"text": "➕ 添加监控",    "callback_data": "§monitor_add"}],
    [{"text": "↩️ 返回",        "callback_data": "§home"}],
]}
KB_HOME = {"inline_keyboard": [
    [{"text": "📊 系统监控", "callback_data": "§menu_monitor"},
     {"text": "🤖 AI 对话", "callback_data": "§menu_ai"}],
    [{"text": "🛠️ 工具箱",  "callback_data": "§menu_tools"},
     {"text": "🎮 游戏",    "callback_data": "§menu_games"}],
    [{"text": "⚙️ 管理面板", "callback_data": "§menu_admin"}],
]}
def kb_guess():
    return {"inline_keyboard": [
        [{"text": str(n), "callback_data": f"§guess_{n}"} for n in [10, 25, 50, 75, 90]],
        [{"text": "↩️ 结束", "callback_data": "§game_end"}],
    ]}

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

# ===================== 权限 =====================
def is_admin(chat_id): return int(chat_id) in ADMIN_IDS
def is_blacklisted(chat_id): return int(chat_id) in load_json(BLACKLIST_FILE, [])

def blacklist_user(chat_id, reason="违规操作"):
    bl = load_json(BLACKLIST_FILE, [])
    if int(chat_id) not in bl:
        bl.append(int(chat_id))
        save_json(BLACKLIST_FILE, bl)
    audit(chat_id, "BLACKLIST", reason)
    log(f"blocked {chat_id}: {reason}")

def audit(chat_id, action, detail, result=""):
    with open(AUDIT_LOG, "a") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"uid={chat_id} action={action} detail={detail!r} result={result!r}\n")

# ===================== Telegram API =====================
def tg_api(method, data=None, files=None, timeout=35):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    if files is None:
        body = json.dumps(data or {}).encode()
        req  = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
    else:
        boundary = "TGBoundary"
        parts = []
        for k, v in (data or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}'.encode())
        for fname, fb in files.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="{fname}"\r\nContent-Type: image/png\r\n\r\n'
                .encode() + fb)
        body = b"\r\n".join(parts) + f"\r\n--{boundary}--\r\n".encode()
        req  = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)

def send_message(chat_id, text, reply_to=None, keyboard=None):
    for i, chunk in enumerate(paginate(text)):
        data = {"chat_id": chat_id, "text": chunk}
        if reply_to and i == 0:
            data["reply_to_message_id"] = reply_to
        if keyboard and i == len(paginate(text)) - 1:
            data["reply_markup"] = keyboard
        try:
            tg_api("sendMessage", data)
        except Exception as e:
            log(f"send failed: {e}")

def send_typing(chat_id):
    """发送「正在输入…」状态指示器"""
    try:
        tg_api("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass

def paginate(text, limit=4000):
    if len(text) <= limit:
        return [text]
    pages = []
    while text:
        if len(text) <= limit:
            pages.append(text); break
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2: cut = limit
        pages.append(text[:cut])
        text = text[cut:].lstrip("\n")
    total = len(pages)
    return [f"[{i+1}/{total}]\n{p}" for i, p in enumerate(pages)]

def answer_callback(cid):
    try: tg_api("answerCallbackQuery", {"callback_query_id": cid})
    except Exception: pass

# ===================== 状态机（持久化） =====================
def _load_ui_states():
    return load_json(UI_STATE_FILE, {})

def _save_ui_states(d):
    save_json(UI_STATE_FILE, d)

def set_state(chat_id, state, extra=None):
    d = _load_ui_states()
    d[str(chat_id)] = {"state": state, "extra": extra}
    _save_ui_states(d)

def get_state(chat_id):
    return _load_ui_states().get(str(chat_id), {})

def clear_state(chat_id):
    d = _load_ui_states()
    d.pop(str(chat_id), None)
    _save_ui_states(d)

# ===================== 游戏状态（持久化） =====================
def _load_game_states():
    return load_json(GAME_STATE_FILE, {})

def _save_game_states(d):
    save_json(GAME_STATE_FILE, d)

def game_set(key, val):
    d = _load_game_states(); d[key] = val; _save_game_states(d)

def game_get(key):
    return _load_game_states().get(key)

def game_del(key):
    d = _load_game_states(); d.pop(key, None); _save_game_states(d)

# ===================== 对话历史（token 截断） =====================
def _est_tokens(text):
    """粗略估算 token 数：英文约 4 字符/token，中文约 1.5 字符/token"""
    cn = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    en = len(text) - cn
    return int(cn / 1.5 + en / 4) + 1

def history_path(chat_id):
    return os.path.join(HISTORY_DIR, f"{chat_id}.json")

def load_history(chat_id):
    return load_json(history_path(chat_id), [])

def save_history(chat_id, history):
    """按 token 数截断：从最旧的记录开始删，保留最近对话"""
    while True:
        total = sum(_est_tokens(e["content"]) for e in history)
        if total <= MAX_HISTORY_TOKENS or len(history) <= 2:
            break
        history = history[2:]  # 每次删一对 user+assistant
    save_json(history_path(chat_id), history)

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

# ===================== 系统信息 =====================
def get_mem_info():
    raw = shell("free -m").splitlines()
    if len(raw) < 2: return None, None, None
    p = raw[1].split(); total, used = int(p[1]), int(p[2])
    return total, used, used * 100 // total

def get_disk_info():
    p = shell("df -h / | tail -1").split()
    return p[1], p[2], p[3], int(p[4].rstrip("%"))

def get_status_text():
    return (f"📊 系统状态\n\n⏰ {shell('uptime')}\n\n"
            f"💾 {shell('free -h | grep Mem')}\n\n"
            f"💿 {shell('df -h / | tail -1')}\n\n"
            f"🔄 AI队列: {executor._work_queue.qsize()} 等待")

def get_mem_text():
    total, used, pct = get_mem_info()
    cpu  = shell("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'")
    load = shell("cat /proc/loadavg")
    swap = shell("free -m | grep Swap")
    top5 = shell("ps aux --sort=-%mem | head -6 | awk '{print $1,$2,$3,$4,$11}' | column -t")
    warn = " ⚠️" if pct and pct >= MEM_ALERT_PCT else ""
    return (f"🧠 内存{warn}\n内存: {used}MB/{total}MB ({pct}%)  CPU: {cpu}%\n"
            f"负载: {load}\nSwap: {swap}\n\nTOP5:\n```\n{top5}\n```")

def get_disk_text():
    total, used, free, pct = get_disk_info()
    shell("sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true")
    warn = " ⚠️" if pct >= DISK_ALERT_PCT else ""
    return (f"💿 磁盘{warn}\n{used}/{total} ({pct}%)  可用: {free}\n\n"
            f"```\n{shell('df -h')}\n```")

def get_net_text():
    ext   = shell("curl -s --max-time 5 https://ifconfig.me 2>/dev/null || echo 获取失败")
    conn  = shell("ss -tun | wc -l")
    ports = shell("ss -tlnp | head -15")
    dns   = shell("grep nameserver /etc/resolv.conf | head -3")
    return (f"🌐 网络\n外网 IP: {ext}\n连接数: {conn}\n\nDNS:\n{dns}\n\n"
            f"监听端口:\n```\n{ports}\n```")

# ===================== Claude 调用 =====================
def ask_claude(prompt, timeout=CLAUDE_TIMEOUT):
    try:
        r = subprocess.run(["claude", "--print", prompt],
                           capture_output=True, text=True, timeout=timeout, cwd=WORKDIR)
        return r.stdout.strip() or r.stderr.strip() or "（无返回，请重试）"
    except subprocess.TimeoutExpired:
        return f"⏱️ 处理超时（{timeout}秒），请简化后重试。"
    except FileNotFoundError:
        return "❌ claude CLI 未找到。"
    except Exception as e:
        log(f"[Claude] unexpected error: {e}")
        return "抱歉，AI 服务暂时不可用，请稍后再试。"

def ai_chat_async(chat_id, msg_id, username, text):
    log(f"[AI] [{username}] {text[:60]}")
    send_typing(chat_id)
    prompt  = build_prompt(chat_id, text)
    reply   = ask_claude(prompt)
    history = load_history(chat_id)
    history.append({"role": "user",      "content": text})
    history.append({"role": "assistant", "content": reply})
    save_history(chat_id, history)
    send_message(chat_id, reply, msg_id)

def ai_code_async(chat_id, msg_id, content):
    send_typing(chat_id)
    prompt = ("你是资深运维工程师和代码专家，请分析以下内容并给出改进建议、"
              "修复方案或漏洞说明（用中文）：\n\n" + content)
    send_message(chat_id, ask_claude(prompt, timeout=60), msg_id)

def ai_talk_async(chat_id, msg_id, content, persona=None):
    send_typing(chat_id)
    reply   = ask_claude(build_prompt(chat_id, content, persona), timeout=60)
    history = load_history(chat_id)
    history.append({"role": "user",      "content": content})
    history.append({"role": "assistant", "content": reply})
    save_history(chat_id, history)
    send_message(chat_id, reply, msg_id)

def ai_tr_async(chat_id, msg_id, text):
    send_typing(chat_id)
    reply = ask_claude(
        "请将以下文本翻译成中文（如果已是中文则翻译成英文），只输出翻译结果：\n\n" + text,
        timeout=30)
    send_message(chat_id, f"🌐 翻译结果:\n{reply}", msg_id)

def handle_file(chat_id, msg_id, file_id, file_name):
    send_typing(chat_id)
    try:
        fp  = tg_api("getFile", {"file_id": file_id})["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{fp}"
        with urllib.request.urlopen(url, timeout=15) as r:
            content = r.read().decode("utf-8", errors="replace")[:8000]
        prompt = (f"请分析以下文件内容（文件名：{file_name}），"
                  f"找出问题、提供优化建议或解读说明：\n\n{content}")
        send_message(chat_id, f"📄 {file_name}\n\n{ask_claude(prompt, timeout=90)}", msg_id)
    except Exception as e:
        log(f"[file] {e}")
        send_message(chat_id, "文件处理失败，请确认文件为文本格式（如 .py .log .conf）。", msg_id)

# ===================== 命令执行（正则黑名单，防绕过） =====================
# 使用正则，忽略空白/大小写，防止 "rm  -rf /" 或 "RM -RF /" 等绕过
_BLOCKED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r"rm\s+-rf\s+/",
    r"dd\s+if=/dev/zero",
    r"mkfs",
    r":\(\)\s*\{.*\}",      # fork 炸弹
    r">\s*/dev/sd[a-z]",
    r"chmod\s+[0-7]*7\s+/",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r">\s*/etc/passwd",
    r">\s*/etc/shadow",
    r"curl.*\|\s*sh",        # 管道安装脚本
    r"wget.*\|\s*sh",
]]

def execute_command(cmd, chat_id):
    for pat in _BLOCKED_PATTERNS:
        if pat.search(cmd):
            blacklist_user(chat_id, f"高危命令: {cmd}")
            return f"⛔ 高危命令已拦截并记录，已加入黑名单。"
    audit(chat_id, "CMD", cmd)
    try:
        r   = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             timeout=30, cwd=WORKDIR)
        out = r.stdout or r.stderr or "(无输出)"
        rc  = "✅ OK" if r.returncode == 0 else f"⚠️ rc={r.returncode}"
        audit(chat_id, "CMD_RESULT", cmd, rc)
        return f"{rc}\n\n```\n{out}\n```"
    except subprocess.TimeoutExpired:
        return "⏱️ 命令执行超时（30秒）"
    except Exception as e:
        log(f"[CMD] error: {e}")
        return "命令执行失败，请检查命令格式。"

# ===================== 游戏 =====================
def game_guess_start(chat_id, msg_id):
    game_set(f"guess_{chat_id}", {"target": random.randint(1, 100), "tries": 0})
    set_state(chat_id, "game_guess")
    send_message(chat_id, "🔢 猜数字！范围 1~100\n点按钮快速选，或直接发数字：",
                 msg_id, keyboard=kb_guess())

def game_guess_input(chat_id, msg_id, val):
    state = game_get(f"guess_{chat_id}")
    if not state:
        send_message(chat_id, "游戏未开始，请点「🔢 猜数字（开始）」", msg_id)
        return
    try: guess = int(val)
    except Exception:
        send_message(chat_id, "请输入数字", msg_id); return
    state["tries"] += 1
    game_set(f"guess_{chat_id}", state)
    t = state["target"]
    if guess == t:
        game_del(f"guess_{chat_id}"); clear_state(chat_id)
        send_message(chat_id, f"🎉 答对！数字是 {t}，共猜 {state['tries']} 次！",
                     msg_id, keyboard=KB_GAMES)
    elif guess < t:
        send_message(chat_id, f"📈 太小了（第 {state['tries']} 次）", msg_id, keyboard=kb_guess())
    else:
        send_message(chat_id, f"📉 太大了（第 {state['tries']} 次）", msg_id, keyboard=kb_guess())

def game_rps(chat_id, msg_id, player):
    choices = {"石头": "✊", "剪刀": "✌️", "布": "🖐️"}
    beats   = {"石头": "剪刀", "剪刀": "布", "布": "石头"}
    if player not in choices:
        send_message(chat_id, "无效选择", msg_id); return
    bot    = random.choice(list(choices.keys()))
    result = "🤝 平局！" if player == bot else ("🎉 你赢！" if beats[player] == bot else "😅 你输了！")
    send_message(chat_id, f"{result}\n你: {choices[player]}{player}  我: {choices[bot]}{bot}",
                 msg_id, keyboard=KB_GAMES)

def game_fortune_async(chat_id, msg_id):
    send_typing(chat_id)
    fortunes = [
        ("大吉", "今日诸事大吉，宜出行、签约、见贵人。"),
        ("吉",   "运势不错，凡事顺遂，适合推进重要计划。"),
        ("中吉", "平稳之日，稳扎稳打，小有收获。"),
        ("小吉", "运势平平，保持平常心，日积月累终有回报。"),
        ("末吉", "稍有波折，凡事三思后行，低调为宜。"),
        ("凶",   "今日需谨慎，避免冲动决策，静待时机。"),
        ("大凶", "诸事不顺，宜静不宜动，待时而变。"),
    ]
    weights = [35, 25, 18, 12, 6, 3, 1]
    seed    = int(hashlib.md5(f"{chat_id}{datetime.now().date()}".encode()).hexdigest(), 16)
    random.seed(seed)
    idx        = random.choices(range(len(fortunes)), weights=weights)[0]
    name, desc = fortunes[idx]
    poem       = ask_claude(f"为运势「{name}」写一句押韵的四字签语，只输出这一句话", timeout=15)
    send_message(chat_id, f"🎋 今日运势\n\n签曰: {name}\n签语: {poem}\n\n{desc}\n\n每日一签，明日再来", msg_id)

# ===================== 工具 =====================
def weather_async(chat_id, msg_id, city):
    send_typing(chat_id)
    if not city:
        send_message(chat_id, "请发送城市名称", msg_id); return
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=4&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            result = r.read().decode("utf-8", errors="replace")
        send_message(chat_id, f"🌤️ {city} 天气\n\n{result}", msg_id)
    except Exception as e:
        log(f"[weather] {e}")
        send_message(chat_id, "天气服务暂时不可用，请稍后再试。", msg_id)

def ip_async(chat_id, msg_id, target):
    send_typing(chat_id)
    if not target:
        send_message(chat_id, f"本机 IP: {shell('curl -s --max-time 8 https://ifconfig.me')}", msg_id)
        return
    result = shell(f"curl -s --max-time 8 'https://ipapi.co/{target}/json/'")
    try:
        d    = json.loads(result)
        text = (f"🔍 {target}\n\nIP: {d.get('ip','')}\n国家: {d.get('country_name','')}\n"
                f"地区: {d.get('region','')}\n城市: {d.get('city','')}\n"
                f"ISP: {d.get('org','')}\n时区: {d.get('timezone','')}")
    except Exception:
        dns  = shell(f"nslookup {target} 2>/dev/null | grep Address | tail -1")
        text = f"🔍 域名解析: {target}\n{dns}"
    send_message(chat_id, text, msg_id)

def qr_async(chat_id, msg_id, content):
    send_typing(chat_id)
    if not content:
        send_message(chat_id, "请发送二维码内容", msg_id); return
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=6, border=4)
        qr.add_data(content); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO(); img.save(buf, format="PNG")
        tg_api("sendPhoto", {"chat_id": chat_id, "caption": f"📷 {content[:50]}"},
               files={"qr.png": buf.getvalue()})
    except Exception as e:
        log(f"[qr] {e}")
        send_message(chat_id, "二维码生成失败，请确认内容格式正确。", msg_id)

# ===================== 定时任务 =====================
def cron_list_text():
    crons = load_json(CRON_FILE, [])
    if not crons: return "暂无定时任务"
    return "⏰ 定时任务:\n\n" + "\n".join(f"ID {c['id']}: [{c['expr']}] {c['cmd']}" for c in crons)

def cron_add(text):
    fields = text.strip().split(None, 5)
    if len(fields) < 6: return "格式: <分 时 日 月 周> <命令>"
    expr, cmd = " ".join(fields[:5]), fields[5]
    crons = load_json(CRON_FILE, [])
    entry = {"id": int(time.time()), "expr": expr, "cmd": cmd,
             "added": datetime.now().isoformat()}
    crons.append(entry)
    save_json(CRON_FILE, crons)
    line = f"{expr} {cmd} >> {WORKDIR}/cron_output.log 2>&1"
    cur  = shell("crontab -l 2>/dev/null || echo ''")
    if line not in cur:
        subprocess.run(["crontab", "-"], input=cur.strip() + "\n" + line + "\n",
                       text=True, capture_output=True)
    return f"✅ 定时任务已添加\n表达式: {expr}\n命令: {cmd}"

# ===================== 网站监控 =====================
def monitor_list_text():
    monitors = load_json(MONITOR_FILE, [])
    if not monitors: return "暂无监控站点"
    lines = ["📡 监控站点:\n"]
    for i, m in enumerate(monitors):
        icon = "🟢" if m.get("status") == "up" else ("🔴" if m.get("status") == "down" else "⚪")
        lines.append(f"{i+1}. {icon} {m['url']}")
    return "\n".join(lines)

def monitor_thread():
    while True:
        try:
            monitors = load_json(MONITOR_FILE, [])
            changed  = False
            for m in monitors:
                old = m.get("status", "unknown")
                try:
                    req = urllib.request.Request(m["url"], headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        new = "up" if r.status < 500 else "down"
                except Exception:
                    new = "down"
                if new != old:
                    changed = True; m["status"] = new
                    label = "🟢 恢复上线" if new == "up" else "🔴 宕机告警"
                    for aid in ADMIN_IDS:
                        send_message(aid, f"📡 {label}\n{m['url']}\n{datetime.now().strftime('%H:%M:%S')}")
            if changed: save_json(MONITOR_FILE, monitors)
        except Exception as e:
            log(f"[Monitor] {e}")
        time.sleep(MONITOR_INTERVAL)

def alert_thread():
    while True:
        try:
            _, _, mem_pct = get_mem_info()
            if mem_pct and mem_pct >= MEM_ALERT_PCT:
                key = f"mem_{mem_pct // 10}"
                if not alert_sent.get(key):
                    for aid in ADMIN_IDS: send_message(aid, f"⚠️ 内存告警: {mem_pct}%")
                    alert_sent[key] = True
            else:
                for k in [k for k in list(alert_sent) if k.startswith("mem_")]: del alert_sent[k]
            _, _, _, disk_pct = get_disk_info()
            if disk_pct >= DISK_ALERT_PCT:
                if not alert_sent.get("disk"):
                    for aid in ADMIN_IDS: send_message(aid, f"⚠️ 磁盘告警: {disk_pct}%")
                    alert_sent["disk"] = True
            else:
                alert_sent.pop("disk", None)
        except Exception as e:
            log(f"[Alert] {e}")
        time.sleep(120)

# ===================== 状态机输入处理 =====================
def handle_state_input(chat_id, msg_id, username, text):
    s     = get_state(chat_id)
    state = s.get("state")
    extra = s.get("extra")
    if not state: return False
    clear_state(chat_id)

    if state == "weather":
        executor.submit(weather_async, chat_id, msg_id, text.strip())
    elif state == "ip":
        executor.submit(ip_async, chat_id, msg_id, text.strip())
    elif state == "qr":
        executor.submit(qr_async, chat_id, msg_id, text.strip())
    elif state == "tr":
        executor.submit(ai_tr_async, chat_id, msg_id, text.strip())
    elif state == "code":
        executor.submit(ai_code_async, chat_id, msg_id, text.strip())
    elif state == "talk_persona":
        set_state(chat_id, "talk", extra=text.strip())
        send_message(chat_id, f"🎭 角色已设定: {text.strip()}\n\n发送对话内容：", msg_id)
    elif state == "talk":
        executor.submit(ai_talk_async, chat_id, msg_id, text.strip(), extra)
    elif state == "cmd":
        if not is_admin(chat_id):
            send_message(chat_id, "⛔ 无权限", msg_id); return True
        send_message(chat_id, f"⚙️ 执行: `{text.strip()}`", msg_id)
        send_message(chat_id, execute_command(text.strip(), chat_id), msg_id)
    elif state == "monitor_add":
        url = text.strip()
        if not url.startswith("http"): url = "https://" + url
        monitors = load_json(MONITOR_FILE, [])
        monitors.append({"url": url, "status": "unknown", "added_by": chat_id})
        save_json(MONITOR_FILE, monitors)
        send_message(chat_id, f"✅ 已添加监控: {url}", msg_id, keyboard=KB_ADMIN)
    elif state == "cron_add":
        send_message(chat_id, cron_add(text.strip()), msg_id, keyboard=KB_ADMIN)
    elif state == "game_guess":
        set_state(chat_id, "game_guess")  # 持续等待猜测
        game_guess_input(chat_id, msg_id, text.strip())
    else:
        return False
    return True

# ===================== 内联回调处理 =====================
def handle_callback(chat_id, msg_id, data):
    if data == "§home":
        send_message(chat_id, "主菜单", msg_id, keyboard=KB_HOME)
    elif data == "§menu_monitor":
        send_message(chat_id, "📊 系统监控", msg_id, keyboard=KB_MONITOR)
    elif data == "§menu_ai":
        h = load_json(history_path(chat_id), [])
        tok = sum(_est_tokens(e["content"]) for e in h)
        send_message(chat_id, f"🤖 AI 对话  |  历史 ~{tok}/{MAX_HISTORY_TOKENS} tokens",
                     msg_id, keyboard=KB_AI)
    elif data == "§menu_tools":
        send_message(chat_id, "🛠️ 工具箱", msg_id, keyboard=KB_TOOLS)
    elif data == "§menu_games":
        send_message(chat_id, "🎮 游戏大厅", msg_id, keyboard=KB_GAMES)
    elif data == "§menu_admin":
        if not is_admin(chat_id): send_message(chat_id, "⛔ 无权限", msg_id); return
        send_message(chat_id, "⚙️ 管理面板", msg_id, keyboard=KB_ADMIN)
    elif data == "§status":
        send_message(chat_id, get_status_text(), msg_id, keyboard=KB_MONITOR)
    elif data == "§mem":
        send_message(chat_id, get_mem_text(), msg_id, keyboard=KB_MONITOR)
    elif data == "§disk":
        send_message(chat_id, get_disk_text(), msg_id, keyboard=KB_MONITOR)
    elif data == "§net":
        send_message(chat_id, get_net_text(), msg_id, keyboard=KB_MONITOR)
    elif data == "§ai_chat":
        clear_state(chat_id)
        send_message(chat_id, "💬 直接发消息，Claude 会回复：", msg_id)
    elif data == "§ai_code":
        set_state(chat_id, "code")
        send_message(chat_id, "🔍 发送要分析的代码或问题：", msg_id)
    elif data == "§ai_tr":
        set_state(chat_id, "tr")
        send_message(chat_id, "🌐 发送要翻译的文本：", msg_id)
    elif data == "§ai_talk":
        set_state(chat_id, "talk_persona")
        send_message(chat_id, "🎭 先发送角色设定（如：你是一个资深运维工程师）：", msg_id)
    elif data == "§clear":
        p = history_path(chat_id)
        if os.path.exists(p): os.remove(p)
        send_message(chat_id, "🧹 对话历史已清除。", msg_id, keyboard=KB_AI)
    elif data == "§weather":
        set_state(chat_id, "weather")
        send_message(chat_id, "🌤️ 发送城市名称：", msg_id)
    elif data == "§ip":
        set_state(chat_id, "ip")
        send_message(chat_id, "🔍 发送 IP 或域名：", msg_id)
    elif data == "§qr":
        set_state(chat_id, "qr")
        send_message(chat_id, "📷 发送二维码内容：", msg_id)
    elif data == "§game_num_new":
        game_guess_start(chat_id, msg_id)
    elif data.startswith("§guess_"):
        game_guess_input(chat_id, msg_id, data.replace("§guess_", ""))
    elif data == "§game_end":
        game_del(f"guess_{chat_id}"); clear_state(chat_id)
        send_message(chat_id, "游戏结束。", msg_id, keyboard=KB_GAMES)
    elif data.startswith("§rps_"):
        game_rps(chat_id, msg_id, data.replace("§rps_", ""))
    elif data == "§fortune":
        executor.submit(game_fortune_async, chat_id, msg_id)
    elif data == "§cmd_input":
        if not is_admin(chat_id): send_message(chat_id, "⛔ 无权限", msg_id); return
        set_state(chat_id, "cmd")
        send_message(chat_id, "💻 发送要执行的 Linux 命令：", msg_id)
    elif data == "§audit":
        if not is_admin(chat_id): send_message(chat_id, "⛔ 无权限", msg_id); return
        lines = shell(f"tail -30 {AUDIT_LOG} 2>/dev/null || echo '暂无日志'")
        send_message(chat_id, f"📋 审计日志:\n\n```\n{lines}\n```", msg_id, keyboard=KB_ADMIN)
    elif data == "§cron_list":
        if not is_admin(chat_id): send_message(chat_id, "⛔ 无权限", msg_id); return
        send_message(chat_id, cron_list_text(), msg_id, keyboard=KB_ADMIN)
    elif data == "§monitor_list":
        send_message(chat_id, monitor_list_text(), msg_id, keyboard=KB_ADMIN)
    elif data == "§monitor_add":
        set_state(chat_id, "monitor_add")
        send_message(chat_id, "📡 发送要监控的 URL：", msg_id)
    elif data == "§help":
        h   = load_json(history_path(chat_id), [])
        tok = sum(_est_tokens(e["content"]) for e in h)
        admin_tip = "\n\n⚙️ 管理面板 → 命令执行/审计/定时/监控" if is_admin(chat_id) else ""
        send_message(chat_id, (
            f"❓ 使用说明 v3.1\n\n"
            f"点底部按钮选择功能，无需输入命令。\n"
            f"💬 普通消息 → Claude AI\n"
            f"📎 发送文件 → 自动分析\n\n"
            f"历史: ~{tok}/{MAX_HISTORY_TOKENS} tokens{admin_tip}"
        ), msg_id, keyboard=REPLY_KEYBOARD)

# ===================== 消息路由 =====================
def process_message(chat_id, username, msg_id, text):
    if is_blacklisted(chat_id):
        send_message(chat_id, "⛔ 你已被限制使用此机器人。"); return
    audit(chat_id, "MSG", text[:100])

    if text in REPLY_BUTTON_MAP:
        handle_callback(chat_id, msg_id, REPLY_BUTTON_MAP[text]); return

    if handle_state_input(chat_id, msg_id, username, text): return

    if text.startswith("/cmd"):
        if not is_admin(chat_id):
            send_message(chat_id, "⛔ /cmd 仅限管理员。", msg_id); return
        cmd = text[4:].strip()
        if cmd:
            send_message(chat_id, f"⚙️ 执行: `{cmd}`", msg_id)
            send_message(chat_id, execute_command(cmd, chat_id), msg_id)
        else:
            set_state(chat_id, "cmd")
            send_message(chat_id, "💻 发送命令：", msg_id)
        return

    if text == "/start":
        send_message(chat_id, "👋 欢迎！点底部按钮选择功能，或直接发消息与 AI 对话。",
                     msg_id, keyboard=REPLY_KEYBOARD); return
    if text == "/clear":
        p = history_path(chat_id)
        if os.path.exists(p): os.remove(p)
        send_message(chat_id, "🧹 对话历史已清除。", msg_id); return

    send_typing(chat_id)
    executor.submit(ai_chat_async, chat_id, msg_id, username, text)

def process_callback(callback):
    cid  = callback["message"]["chat"]["id"]
    mid  = callback["message"]["message_id"]
    data = callback.get("data", "")
    answer_callback(callback["id"])
    if data.startswith("§"):
        handle_callback(cid, mid, data)

# ===================== 长轮询主循环 =====================
def load_state():  return load_json(STATE_FILE, {"last_update_id": 0})
def save_state(s):
    with state_lock: save_json(STATE_FILE, s)

def process_updates():
    global last_heartbeat
    state  = load_state()
    params = {"limit": 20, "timeout": LONG_POLL_TIMEOUT}  # 长轮询
    if state["last_update_id"]:
        params["offset"] = state["last_update_id"] + 1

    try:
        updates = tg_api("getUpdates", params,
                         timeout=LONG_POLL_TIMEOUT + 5).get("result", [])
    except urllib.error.URLError as e:
        log(f"poll network error: {e}"); return
    except Exception as e:
        log(f"poll error: {e}"); return

    for update in updates:
        uid = update["update_id"]
        state["last_update_id"] = max(state.get("last_update_id", 0), uid)

        if "callback_query" in update:
            try: process_callback(update["callback_query"])
            except Exception as e: log(f"callback error: {e}")
            continue

        msg       = update.get("message", {})
        text      = msg.get("text", "")
        chat_id   = msg.get("chat", {}).get("id")
        username  = msg.get("from", {}).get("first_name", "用户")
        msg_id    = msg.get("message_id")
        chat_type = msg.get("chat", {}).get("type", "private")

        if not chat_id: continue

        if chat_type in ("group", "supergroup") and text and text.startswith("/cmd"):
            if not is_admin(chat_id):
                tg_api("sendMessage", {"chat_id": chat_id, "text": "⛔ 群内禁止执行服务器命令。",
                                       "reply_to_message_id": msg_id}); continue

        for member in msg.get("new_chat_members", []):
            tg_api("sendMessage", {"chat_id": chat_id,
                "text": f"👋 欢迎 {member.get('first_name','新朋友')} 加入！点 ❓ 帮助 查看功能。"})

        doc = msg.get("document")
        if doc:
            executor.submit(handle_file, chat_id, msg_id,
                            doc["file_id"], doc.get("file_name", "file")); continue

        if not text: continue
        try: process_message(chat_id, username, msg_id, text)
        except Exception as e: log(f"process error: {e}")

    save_state(state)
    now = time.time()
    if now - last_heartbeat > HEARTBEAT_INTERVAL:
        log(f"heartbeat offset={state.get('last_update_id',0)} "
            f"tokens_limit={MAX_HISTORY_TOKENS}")
        last_heartbeat = now

def cleanup_lock():
    if os.path.exists(LOCK_FILE):
        if time.time() - os.path.getmtime(LOCK_FILE) > 90:
            os.remove(LOCK_FILE); return True
        log("already running, exit"); return False
    return True

def main():
    if not cleanup_lock(): exit(0)
    open(LOCK_FILE, "w").close()
    log(f"Bot v3.1 started | admins={ADMIN_IDS} | long_poll={LONG_POLL_TIMEOUT}s "
        f"| history_tokens={MAX_HISTORY_TOKENS}")
    threading.Thread(target=monitor_thread, daemon=True).start()
    threading.Thread(target=alert_thread,   daemon=True).start()
    try:
        while True:
            process_updates()   # 长轮询：阻塞等待 30s，有消息立即返回
    except KeyboardInterrupt:
        log("stopped")
    finally:
        executor.shutdown(wait=False)
        if os.path.exists(LOCK_FILE): os.remove(LOCK_FILE)

if __name__ == "__main__":
    main()
