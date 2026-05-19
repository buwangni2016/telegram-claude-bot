"""
security.py - 安全模块 (v2-secure / v3-full)
包含: 管理员权限 / 黑名单 / 审计日志 / 命令执行 / 群聊限制
"""

import os
import subprocess
from datetime import datetime
from modules.core import load_json, save_json, log, WORKDIR, shell

# ===================== 配置 =====================
_cfg_file   = os.environ.get("BOT_CONFIG", "")
_cfg        = load_json(_cfg_file, {}) if _cfg_file else {}
ADMIN_IDS   = set(_cfg.get("ADMIN_IDS", [7499029810]))
AUDIT_LOG   = os.path.join(WORKDIR, "audit.log")
BLACKLIST_FILE = os.path.join(WORKDIR, "blacklist.json")

BLOCKED_CMDS = [
    "rm -rf /", "dd if=/dev/zero", "mkfs", ":(){ :|:& };:",
    "> /dev/sda", "chmod 777 /", "shutdown", "reboot", "halt",
]

# ===================== 权限检查 =====================
def is_admin(chat_id):
    return int(chat_id) in ADMIN_IDS

def is_blacklisted(chat_id):
    return int(chat_id) in load_json(BLACKLIST_FILE, [])

def blacklist_user(chat_id, reason="违规操作"):
    bl = load_json(BLACKLIST_FILE, [])
    if int(chat_id) not in bl:
        bl.append(int(chat_id))
        save_json(BLACKLIST_FILE, bl)
    audit(chat_id, "BLACKLIST", reason, "自动拉黑")
    log(f"[Security] blocked {chat_id}: {reason}")

# ===================== 审计日志 =====================
def audit(chat_id, action, detail, result=""):
    line = (f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"uid={chat_id} action={action} detail={detail!r} result={result!r}\n")
    with open(AUDIT_LOG, "a") as f:
        f.write(line)

def get_audit_tail(n=30):
    if not os.path.exists(AUDIT_LOG):
        return "暂无日志"
    return shell(f"tail -{n} {AUDIT_LOG}")

# ===================== 命令执行 =====================
def execute_command(cmd, chat_id):
    for kw in BLOCKED_CMDS:
        if kw.lower() in cmd.lower():
            blacklist_user(chat_id, f"高危命令: {cmd}")
            return f"⛔ 高危命令已拦截，已加入黑名单: {kw}"
    audit(chat_id, "CMD", cmd)
    try:
        r   = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             timeout=30, cwd=WORKDIR)
        out = r.stdout or r.stderr or "(无输出)"
        rc  = "✅ OK" if r.returncode == 0 else f"⚠️ rc={r.returncode}"
        audit(chat_id, "CMD_RESULT", cmd, rc)
        return f"{rc}\n\n```\n{out}\n```"
    except subprocess.TimeoutExpired:
        return "⏱️ 执行超时（30秒）"
    except Exception as e:
        return f"❌ {e}"
