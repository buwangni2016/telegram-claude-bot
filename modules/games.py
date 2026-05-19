"""
games.py - 游戏娱乐模块 (v3-full)
包含: 猜数字 / 石头剪刀布 / 今日运势抽签
"""

import hashlib
import random
from datetime import datetime
from modules.core import ask_claude, send_message, log

# 每个用户的游戏内存状态（进程内）
_game_states = {}

# ===================== 猜数字 =====================
def game_guess_start(chat_id, msg_id):
    _game_states[f"guess_{chat_id}"] = {"target": random.randint(1, 100), "tries": 0}
    send_message(chat_id,
        "🔢 猜数字开始！范围 1~100\n点快捷按钮或直接发送数字猜测：",
        msg_id, keyboard=_kb_guess())

def game_guess_input(chat_id, msg_id, val):
    state = _game_states.get(f"guess_{chat_id}")
    if not state:
        send_message(chat_id, "游戏未开始，请点「🔢 猜数字（开始）」", msg_id)
        return False
    try:
        guess = int(val)
    except Exception:
        send_message(chat_id, "请输入数字", msg_id)
        return False
    state["tries"] += 1
    t = state["target"]
    if guess == t:
        del _game_states[f"guess_{chat_id}"]
        send_message(chat_id,
            f"🎉 答对了！数字是 {t}，共猜了 {state['tries']} 次！",
            msg_id, keyboard=_kb_games())
        return True  # 游戏结束
    elif guess < t:
        send_message(chat_id, f"📈 太小了！（第 {state['tries']} 次）", msg_id, keyboard=_kb_guess())
    else:
        send_message(chat_id, f"📉 太大了！（第 {state['tries']} 次）", msg_id, keyboard=_kb_guess())
    return False

def game_guess_active(chat_id):
    return f"guess_{chat_id}" in _game_states

def game_guess_end(chat_id):
    _game_states.pop(f"guess_{chat_id}", None)

# ===================== 石头剪刀布 =====================
def game_rps(chat_id, msg_id, player):
    choices = {"石头": "✊", "剪刀": "✌️", "布": "🖐️"}
    beats   = {"石头": "剪刀", "剪刀": "布", "布": "石头"}
    if player not in choices:
        send_message(chat_id, "无效选择", msg_id)
        return
    bot    = random.choice(list(choices.keys()))
    result = "🤝 平局！" if player == bot else ("🎉 你赢了！" if beats[player] == bot else "😅 你输了！")
    send_message(chat_id,
        f"{result}\n你: {choices[player]} {player}  我: {choices[bot]} {bot}",
        msg_id, keyboard=_kb_games())

# ===================== 今日运势 =====================
def game_fortune_async(chat_id, msg_id):
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
    send_message(chat_id,
        f"🎋 今日运势\n\n签曰: {name}\n签语: {poem}\n\n{desc}\n\n每日一签，明日再来",
        msg_id)

# ===================== 内部键盘引用 (避免循环导入) =====================
def _kb_guess():
    return {
        "inline_keyboard": [
            [{"text": str(n), "callback_data": f"§guess_{n}"}
             for n in [10, 25, 50, 75, 90]],
            [{"text": "↩️ 结束游戏", "callback_data": "§game_end"}],
        ]
    }

def _kb_games():
    return {
        "inline_keyboard": [
            [{"text": "🔢 猜数字（开始）", "callback_data": "§game_num_new"}],
            [{"text": "✊ 石头", "callback_data": "§rps_石头"},
             {"text": "✌️ 剪刀", "callback_data": "§rps_剪刀"},
             {"text": "🖐️ 布",   "callback_data": "§rps_布"}],
            [{"text": "🎋 今日运势", "callback_data": "§fortune"}],
            [{"text": "↩️ 返回",    "callback_data": "§home"}],
        ]
    }
