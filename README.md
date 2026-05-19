# Telegram Claude Bot

基于 Vercel 沙箱环境的 Telegram 远程控制 Bot，集成 Claude AI 智能对话与 Linux 终端命令执行能力。

## 功能特性

- **`/cmd <命令>`** — 直接执行 Linux 终端命令，实时返回结果
- **普通消息** — 调用 `claude --print` 生成智能回复，具备完整工具执行能力（读写文件、调用 API 等）
- **PM2 托管** — 进程崩溃自动重启，内存超限自动重启
- **双层保活** — PM2 守护 + 定时心跳脚本，防止沙箱休眠
- **并发处理** — 线程池异步处理 AI 消息，`/cmd` 命令不受阻塞
- **安全防护** — 高危命令黑名单拦截，执行超时限制

## 快速开始

### 一键部署

```bash
bash setup.sh <YOUR_BOT_TOKEN>
```

不带参数时使用脚本内置 Token：

```bash
bash setup.sh
```

### 环境要求

| 依赖 | 说明 |
|------|------|
| Python 3.x | 运行 Bot 主脚本 |
| PM2 | 进程管理 |
| claude CLI | AI 回复能力（Anthropic Claude Code）|

### Bot 使用

| 指令 | 说明 |
|------|------|
| `/start` | 显示欢迎信息 |
| `/cmd <命令>` | 执行 Linux 命令 |
| `/status` | 查看系统状态 |
| `/help` | 完整使用说明 |
| 普通文字 | Claude AI 智能回复 |

**命令示例：**

```
/cmd ls -lah
/cmd df -h
/cmd ps aux | head -10
/cmd cat /etc/os-release
帮我查看当前运行的进程
今天几号
```

## 项目结构

```
telegram-claude-bot/
├── README.md          # 项目说明（本文件）
├── bot.py             # Bot 主脚本
├── setup.sh           # 一键部署脚本
├── keepalive.sh       # 保活脚本
└── docs/
    └── architecture.md # 架构说明与迭代指南
```

## 架构说明

```
Telegram 消息
    │
    ▼
Bot 主循环（2s 轮询）
    │
    ├── /cmd 命令 ──────── subprocess 同步执行 ──── 立即回复
    │
    └── 普通消息 ──────── ThreadPoolExecutor(3)
                              │
                              ▼
                        claude --print
                        （独立进程，带工具能力）
                              │
                              ▼
                           回复用户
    
PM2 守护进程
    └── 崩溃自动重启
    └── 内存 > 200MB 自动重启

Cron 定时任务（每5分钟）
    └── keepalive.sh
        └── 检测 PM2 进程
        └── 异常时自动重启
```

## 管理命令

```bash
# 查看进程状态
pm2 list

# 查看实时日志
pm2 logs telegram-remote

# 重启 Bot
pm2 restart telegram-remote

# 停止 Bot
pm2 stop telegram-remote

# 手动执行保活
bash keepalive.sh
```

## 注意事项

- **Cron 保活任务有效期 7 天**，到期后需在 Claude 会话中重新创建
- 禁止执行高危命令：`rm -rf /`、`mkfs`、`dd if=/dev/zero` 等
- AI 处理超时限制 120 秒，命令执行超时限制 30 秒
- 同时最多处理 3 条 AI 消息（可在 `bot.py` 中调整 `MAX_AI_WORKERS`）

## 迭代指南

详见 [docs/architecture.md](docs/architecture.md)

## License

MIT
