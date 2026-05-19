"""
monitoring.py - 监控模块 (v2-secure / v3-full)
包含: 系统状态 / 内存磁盘网络 / 后台告警线程 / 网站监控
"""

import os
import time
import threading
import urllib.request
from datetime import datetime
from modules.core import load_json, save_json, log, shell, send_message, WORKDIR

# ===================== 配置 =====================
_cfg_file        = os.environ.get("BOT_CONFIG", "")
_cfg             = load_json(_cfg_file, {}) if _cfg_file else {}
ADMIN_IDS        = set(_cfg.get("ADMIN_IDS", [7499029810]))
MEM_ALERT_PCT    = _cfg.get("MEM_ALERT_PCT", 85)
DISK_ALERT_PCT   = _cfg.get("DISK_ALERT_PCT", 85)
MONITOR_INTERVAL = _cfg.get("MONITOR_INTERVAL", 60)
MONITOR_FILE     = os.path.join(WORKDIR, "site_monitor.json")

_alert_sent = {}

# ===================== 系统信息 =====================
def get_mem_info():
    raw   = shell("free -m")
    lines = raw.splitlines()
    if len(lines) < 2:
        return None, None, None
    parts = lines[1].split()
    total, used = int(parts[1]), int(parts[2])
    return total, used, used * 100 // total

def get_disk_info():
    parts = shell("df -h / | tail -1").split()
    return parts[1], parts[2], parts[3], int(parts[4].rstrip("%"))

def get_status_text(ai_queue_size=0):
    return (
        f"📊 系统状态\n\n"
        f"⏰ {shell('uptime')}\n\n"
        f"💾 {shell('free -h | grep Mem')}\n\n"
        f"💿 {shell('df -h / | tail -1')}\n\n"
        f"🔄 AI队列: {ai_queue_size} 等待"
    )

def get_mem_text():
    total, used, pct = get_mem_info()
    cpu  = shell("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'")
    load = shell("cat /proc/loadavg")
    swap = shell("free -m | grep Swap")
    top5 = shell("ps aux --sort=-%mem | head -6 | awk '{print $1,$2,$3,$4,$11}' | column -t")
    warn = " ⚠️" if pct and pct >= MEM_ALERT_PCT else ""
    return (
        f"🧠 内存状态{warn}\n\n"
        f"内存: {used}MB/{total}MB ({pct}%)  CPU: {cpu}%\n"
        f"负载: {load}\nSwap: {swap}\n\n"
        f"内存 TOP5:\n```\n{top5}\n```"
    )

def get_disk_text():
    total, used, free, pct = get_disk_info()
    df_full = shell("df -h")
    shell("sync && echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true")
    warn = " ⚠️" if pct >= DISK_ALERT_PCT else ""
    return (
        f"💿 磁盘状态{warn}\n\n"
        f"根分区: {used}/{total} ({pct}%)  可用: {free}\n\n"
        f"全部分区:\n```\n{df_full}\n```"
    )

def get_net_text():
    ext   = shell("curl -s --max-time 5 https://ifconfig.me 2>/dev/null || echo 获取失败")
    conn  = shell("ss -tun | wc -l")
    ports = shell("ss -tlnp | head -15")
    dns   = shell("grep nameserver /etc/resolv.conf | head -3")
    return (
        f"🌐 网络状态\n\n外网 IP: {ext}\n当前连接数: {conn}\n\n"
        f"DNS:\n{dns}\n\n监听端口:\n```\n{ports}\n```"
    )

# ===================== 网站监控管理 =====================
def monitor_list_text():
    monitors = load_json(MONITOR_FILE, [])
    if not monitors:
        return "暂无监控站点"
    lines = ["📡 监控站点:\n"]
    for i, m in enumerate(monitors):
        icon = "🟢" if m.get("status") == "up" else ("🔴" if m.get("status") == "down" else "⚪")
        lines.append(f"{i+1}. {icon} {m['url']}")
    return "\n".join(lines)

def monitor_add(url, chat_id):
    if not url.startswith("http"):
        url = "https://" + url
    monitors = load_json(MONITOR_FILE, [])
    monitors.append({"url": url, "status": "unknown", "added_by": chat_id})
    save_json(MONITOR_FILE, monitors)
    return f"✅ 已添加监控: {url}"

def monitor_del(idx):
    monitors = load_json(MONITOR_FILE, [])
    try:
        removed = monitors.pop(idx - 1)
        save_json(MONITOR_FILE, monitors)
        return f"✅ 已移除: {removed['url']}"
    except Exception:
        return "❌ 序号无效"

# ===================== 后台监控线程 =====================
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
                    changed    = True
                    m["status"] = new
                    label = "🟢 恢复上线" if new == "up" else "🔴 宕机告警"
                    for aid in ADMIN_IDS:
                        send_message(aid,
                            f"📡 站点监控 {label}\n{m['url']}\n"
                            f"{datetime.now().strftime('%H:%M:%S')}")
            if changed:
                save_json(MONITOR_FILE, monitors)
        except Exception as e:
            log(f"[Monitor] {e}")
        time.sleep(MONITOR_INTERVAL)

def alert_thread():
    while True:
        try:
            _, _, mem_pct = get_mem_info()
            if mem_pct and mem_pct >= MEM_ALERT_PCT:
                key = f"mem_{mem_pct // 10}"
                if not _alert_sent.get(key):
                    for aid in ADMIN_IDS:
                        send_message(aid, f"⚠️ 内存告警！使用率: {mem_pct}%，请及时处理。")
                    _alert_sent[key] = True
            else:
                for k in [k for k in list(_alert_sent) if k.startswith("mem_")]:
                    del _alert_sent[k]

            _, _, _, disk_pct = get_disk_info()
            if disk_pct >= DISK_ALERT_PCT:
                if not _alert_sent.get("disk"):
                    for aid in ADMIN_IDS:
                        send_message(aid, f"⚠️ 磁盘告警！使用率: {disk_pct}%，请及时清理。")
                    _alert_sent["disk"] = True
            else:
                _alert_sent.pop("disk", None)
        except Exception as e:
            log(f"[Alert] {e}")
        time.sleep(120)

def start_background_threads():
    threading.Thread(target=monitor_thread, daemon=True).start()
    threading.Thread(target=alert_thread,   daemon=True).start()
    log("[Monitoring] Background threads started")
