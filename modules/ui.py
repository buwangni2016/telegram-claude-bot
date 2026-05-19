"""
ui.py - 图形界面模块 (v3-full)
包含: 持久底部键盘 / 内联子菜单 / 用户状态机
"""

# ===================== 底部持久键盘 =====================
REPLY_KEYBOARD = {
    "keyboard": [
        ["📊 系统监控", "🤖 AI 对话"],
        ["🛠️ 工具箱",  "🎮 游戏"],
        ["⚙️ 管理面板", "❓ 帮助"],
    ],
    "resize_keyboard": True,
    "persistent": True,
}

# 底部按钮文字 → 内联回调映射
REPLY_BUTTON_MAP = {
    "📊 系统监控": "§menu_monitor",
    "🤖 AI 对话":  "§menu_ai",
    "🛠️ 工具箱":  "§menu_tools",
    "🎮 游戏":     "§menu_games",
    "⚙️ 管理面板": "§menu_admin",
    "❓ 帮助":     "§help",
}

# ===================== 内联子菜单 =====================
KB_MONITOR = {
    "inline_keyboard": [
        [{"text": "📊 状态总览", "callback_data": "§status"},
         {"text": "🧠 内存",    "callback_data": "§mem"}],
        [{"text": "💿 磁盘",    "callback_data": "§disk"},
         {"text": "🌐 网络",    "callback_data": "§net"}],
        [{"text": "↩️ 返回主菜单", "callback_data": "§home"}],
    ]
}

KB_AI = {
    "inline_keyboard": [
        [{"text": "💬 智能对话",  "callback_data": "§ai_chat"},
         {"text": "🔍 代码分析", "callback_data": "§ai_code"}],
        [{"text": "🌐 翻译",      "callback_data": "§ai_tr"},
         {"text": "🎭 角色扮演", "callback_data": "§ai_talk"}],
        [{"text": "🧹 清除历史", "callback_data": "§clear"},
         {"text": "↩️ 返回",     "callback_data": "§home"}],
    ]
}

KB_TOOLS = {
    "inline_keyboard": [
        [{"text": "🌤️ 天气查询", "callback_data": "§weather"},
         {"text": "🔍 IP查询",   "callback_data": "§ip"}],
        [{"text": "📷 生成二维码", "callback_data": "§qr"},
         {"text": "🌐 翻译",      "callback_data": "§ai_tr"}],
        [{"text": "↩️ 返回",      "callback_data": "§home"}],
    ]
}

KB_GAMES = {
    "inline_keyboard": [
        [{"text": "🔢 猜数字（开始）", "callback_data": "§game_num_new"}],
        [{"text": "✊ 石头",  "callback_data": "§rps_石头"},
         {"text": "✌️ 剪刀", "callback_data": "§rps_剪刀"},
         {"text": "🖐️ 布",   "callback_data": "§rps_布"}],
        [{"text": "🎋 今日运势", "callback_data": "§fortune"}],
        [{"text": "↩️ 返回",    "callback_data": "§home"}],
    ]
}

KB_ADMIN = {
    "inline_keyboard": [
        [{"text": "💻 执行命令",     "callback_data": "§cmd_input"},
         {"text": "📋 审计日志",    "callback_data": "§audit"}],
        [{"text": "⏰ 定时任务列表", "callback_data": "§cron_list"},
         {"text": "📡 监控站点",    "callback_data": "§monitor_list"}],
        [{"text": "➕ 添加监控站点", "callback_data": "§monitor_add"}],
        [{"text": "↩️ 返回",        "callback_data": "§home"}],
    ]
}

KB_HOME = {
    "inline_keyboard": [
        [{"text": "📊 系统监控", "callback_data": "§menu_monitor"},
         {"text": "🤖 AI 对话", "callback_data": "§menu_ai"}],
        [{"text": "🛠️ 工具箱",  "callback_data": "§menu_tools"},
         {"text": "🎮 游戏",    "callback_data": "§menu_games"}],
        [{"text": "⚙️ 管理面板", "callback_data": "§menu_admin"}],
    ]
}

def kb_guess():
    return {
        "inline_keyboard": [
            [{"text": str(n), "callback_data": f"§guess_{n}"}
             for n in [10, 25, 50, 75, 90]],
            [{"text": "↩️ 结束游戏", "callback_data": "§game_end"}],
        ]
    }

# ===================== 用户状态机 =====================
_user_states = {}

def set_state(chat_id, state, extra=None):
    _user_states[chat_id] = {"state": state, "extra": extra}

def get_state(chat_id):
    return _user_states.get(chat_id, {})

def clear_state(chat_id):
    _user_states.pop(chat_id, None)
