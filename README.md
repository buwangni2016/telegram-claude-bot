# Telegram Claude Bot

基于 Vercel 沙箱环境的 Telegram 远程控制 Bot，集成 Claude AI 智能对话与 Linux 终端命令执行能力。

## 版本说明

本项目采用多分支隔离管理三个功能层级，按需选择：

| 分支 | 版本 | 定位 | 适合人群 |
|------|------|------|----------|
| `v1-simple` | 1.x | 极简内核版 | 只需 AI 对话 + 命令执行 |
| `v2-secure` | 2.x | 安全增强版 | 需要权限管理 + 系统监控 |
| `v3-full`   | 3.x | 全功能娱乐版 | 需要完整功能 + 图形界面 |

## 功能对比

| 功能 | v1-simple | v2-secure | v3-full |
|------|:---------:|:---------:|:-------:|
| AI 智能对话（多轮记忆）| ✅ | ✅ | ✅ |
| /cmd 终端命令执行 | ✅ | ✅ | ✅ |
| 管理员权限分级 | ✅ | ✅ | ✅ |
| 用户黑名单 + 审计日志 | ❌ | ✅ | ✅ |
| 系统监控 /status /mem /disk /net | ❌ | ✅ | ✅ |
| 内存/磁盘后台告警 | ❌ | ✅ | ✅ |
| 图形底部键盘菜单 | ❌ | ❌ | ✅ |
| 游戏（猜数字/石头剪刀布/运势）| ❌ | ❌ | ✅ |
| 工具箱（天气/IP/二维码/翻译）| ❌ | ❌ | ✅ |
| 网站监控 + 定时任务管理 | ❌ | ❌ | ✅ |
| 文件上传自动分析 | ❌ | ❌ | ✅ |

## 快速开始

```bash
# 克隆项目
git clone https://github.com/buwangni2016/telegram-claude-bot.git
cd telegram-claude-bot

# v1 极简版
git checkout v1-simple && bash scripts/setup_v1.sh <BOT_TOKEN>

# v2 安全版
git checkout v2-secure && bash scripts/setup_v2.sh <BOT_TOKEN>

# v3 全功能版（推荐）
git checkout v3-full && bash scripts/setup_v3.sh <BOT_TOKEN>
```

## 项目结构

```
telegram-claude-bot/
├── modules/
│   ├── core.py         # 核心通用模块（所有版本）
│   ├── security.py     # 安全模块（v2+）
│   ├── monitoring.py   # 监控模块（v2+）
│   ├── games.py        # 游戏模块（v3）
│   ├── tools.py        # 工具模块（v3）
│   └── ui.py           # 图形界面模块（v3）
├── config/
│   ├── v1.json         # v1 配置
│   ├── v2.json         # v2 配置
│   └── v3.json         # v3 配置
├── scripts/
│   ├── setup_v1.sh
│   ├── setup_v2.sh
│   └── setup_v3.sh
├── bot_v1.py / bot_v2.py / bot_v3.py
├── keepalive.sh
└── CHANGELOG.md
```

## 分支管理规范

```
main  ──────────────────────────────── 文档 & 共享结构
  │
  ├── v1-simple (tag: v1.0.0)  极简内核
  │       ↓ cherry-pick bug fixes
  ├── v2-secure (tag: v2.0.0)  安全增强
  │       ↓ cherry-pick bug fixes
  └── v3-full   (tag: v3.0.0)  全功能版
```

Bug 修复流向：`main → v1-simple → v2-secure → v3-full`

## 环境要求

| 依赖 | 说明 |
|------|------|
| Python 3.x | Bot 主脚本 |
| PM2 | 进程管理 |
| claude CLI | Claude Code，提供 AI 能力 |
| qrcode + Pillow | 仅 v3-full 需要 |

## 进程管理

```bash
pm2 logs telegram-remote
pm2 restart telegram-remote
pm2 status
```

## License

MIT
