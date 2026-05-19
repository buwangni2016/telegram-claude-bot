"""
tools.py - 拓展工具模块 (v3-full)
包含: 天气 / IP查询 / 二维码 / 翻译 / 文件分析 / 定时任务管理
"""

import io
import json
import os
import subprocess
import time
import urllib.request
import urllib.parse
from datetime import datetime
from modules.core import ask_claude, send_message, log, shell, load_json, save_json, WORKDIR

CRON_FILE = os.path.join(WORKDIR, "user_crons.json")

# ===================== 天气 =====================
def weather_async(chat_id, msg_id, city):
    if not city:
        send_message(chat_id, "请发送城市名称", msg_id)
        return
    try:
        url = f"https://wttr.in/{urllib.parse.quote(city)}?format=4&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            result = r.read().decode("utf-8", errors="replace")
        send_message(chat_id, f"🌤️ {city} 天气\n\n{result}", msg_id)
    except Exception as e:
        send_message(chat_id, f"获取失败: {e}", msg_id)

# ===================== IP / 域名查询 =====================
def ip_async(chat_id, msg_id, target):
    if not target:
        result = shell("curl -s --max-time 8 https://ifconfig.me")
        send_message(chat_id, f"🌐 本机外网 IP: {result}", msg_id)
        return
    result = shell(f"curl -s --max-time 8 'https://ipapi.co/{target}/json/'")
    try:
        d    = json.loads(result)
        text = (
            f"🔍 IP 查询: {target}\n\n"
            f"IP: {d.get('ip','')}\n国家: {d.get('country_name','')}\n"
            f"地区: {d.get('region','')}\n城市: {d.get('city','')}\n"
            f"ISP: {d.get('org','')}\n时区: {d.get('timezone','')}"
        )
    except Exception:
        dns  = shell(f"nslookup {target} 2>/dev/null | grep Address | tail -1")
        text = f"🔍 域名解析: {target}\n{dns}"
    send_message(chat_id, text, msg_id)

# ===================== 二维码 =====================
def qr_async(chat_id, msg_id, content, tg_api_func):
    if not content:
        send_message(chat_id, "请发送二维码内容", msg_id)
        return
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=6, border=4)
        qr.add_data(content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        tg_api_func("sendPhoto",
                    {"chat_id": chat_id, "caption": f"📷 QR码: {content[:50]}"},
                    files={"qr.png": buf.getvalue()})
    except Exception as e:
        send_message(chat_id, f"QR生成失败: {e}", msg_id)

# ===================== 翻译 =====================
def tr_async(chat_id, msg_id, text):
    if not text:
        send_message(chat_id, "请发送要翻译的文本", msg_id)
        return
    reply = ask_claude(
        "请将以下文本翻译成中文（如果已是中文则翻译成英文），只输出翻译结果：\n\n" + text,
        timeout=30)
    send_message(chat_id, f"🌐 翻译结果:\n{reply}", msg_id)

# ===================== 代码分析 =====================
def code_async(chat_id, msg_id, content):
    prompt = (
        "你是资深运维工程师和代码专家，请分析以下内容并给出改进建议、"
        "修复方案或漏洞说明（用中文）：\n\n" + content
    )
    send_message(chat_id, ask_claude(prompt, timeout=60), msg_id)

# ===================== 角色对话 =====================
def talk_async(chat_id, msg_id, content, persona=None):
    from modules.core import build_prompt, load_history, save_history
    reply   = ask_claude(build_prompt(chat_id, content, persona), timeout=60)
    history = load_history(chat_id)
    history.append({"role": "user",      "content": content})
    history.append({"role": "assistant", "content": reply})
    save_history(chat_id, history)
    send_message(chat_id, reply, msg_id)

# ===================== 文件分析 =====================
def handle_file(chat_id, msg_id, file_id, file_name, bot_token):
    try:
        import urllib.request as ur
        fp  = __import__("json").loads(
            ur.urlopen(
                f"https://api.telegram.org/bot{bot_token}/getFile",
                data=json.dumps({"file_id": file_id}).encode()
            ).read()
        )["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{bot_token}/{fp}"
        with ur.urlopen(url, timeout=15) as r:
            content = r.read().decode("utf-8", errors="replace")[:8000]
        prompt = (
            f"请分析以下文件内容（文件名：{file_name}），"
            f"找出问题、提供优化建议或解读说明：\n\n{content}"
        )
        send_message(chat_id, f"📄 文件分析: {file_name}\n\n{ask_claude(prompt, timeout=90)}", msg_id)
    except Exception as e:
        send_message(chat_id, f"文件处理失败: {e}", msg_id)

# ===================== 定时任务 =====================
def cron_list_text():
    crons = load_json(CRON_FILE, [])
    if not crons:
        return "暂无定时任务"
    return "⏰ 定时任务列表:\n\n" + "\n".join(
        f"ID {c['id']}: [{c['expr']}] {c['cmd']}" for c in crons)

def cron_add(expr_cmd):
    fields = expr_cmd.strip().split(None, 5)
    if len(fields) < 6:
        return "格式: <分 时 日 月 周> <命令>"
    expr, cmd = " ".join(fields[:5]), fields[5]
    crons = load_json(CRON_FILE, [])
    entry = {"id": int(time.time()), "expr": expr, "cmd": cmd,
             "added": datetime.now().isoformat()}
    crons.append(entry)
    save_json(CRON_FILE, crons)
    line    = f"{expr} {cmd} >> {WORKDIR}/cron_output.log 2>&1"
    current = shell("crontab -l 2>/dev/null || echo ''")
    if line not in current:
        subprocess.run(["crontab", "-"],
                       input=current.strip() + "\n" + line + "\n",
                       text=True, capture_output=True)
    return f"✅ 定时任务已添加\n表达式: {expr}\n命令: {cmd}"

def cron_del(cid):
    crons  = load_json(CRON_FILE, [])
    before = len(crons)
    crons  = [c for c in crons if c["id"] != int(cid)]
    save_json(CRON_FILE, crons)
    return f"✅ 任务 {cid} 已删除" if len(crons) < before else f"❌ 未找到任务 {cid}"
