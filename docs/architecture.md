# 架构说明与迭代指南

## 工作原理

### 消息处理流程

1. Bot 每 2 秒轮询一次 Telegram API（`getUpdates`）
2. 根据消息类型分发处理：
   - `/cmd` → `subprocess.run()` 同步执行，立即回复
   - 普通消息 → `ThreadPoolExecutor` 提交异步任务，调用 `claude --print`
3. `claude --print` 是独立进程，拥有完整工具能力（Bash/Read/Write/Grep 等）
4. 处理完成后通过 `sendMessage` 回复用户

### 保活机制

**第一层：PM2 进程守护**
- 进程崩溃自动重启（延迟 3 秒）
- 内存超过 200MB 自动重启
- `pm2 save` 持久化配置

**第二层：定时心跳脚本**
- 每 5 分钟执行 `keepalive.sh`
- 检测 `telegram-remote` 进程是否在线
- 异常时调用 `pm2 restart` 恢复
- 心跳日志保留最近 500 行

### 锁文件机制

`telegram_remote.lock` 防止重复启动：
- 启动时检查锁文件年龄
- 超过 90 秒视为残留（PM2 崩溃重启场景），自动清理
- 正常退出时删除锁文件

## 关键配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `POLL_INTERVAL` | `2` 秒 | Telegram 消息轮询间隔 |
| `CLAUDE_TIMEOUT` | `120` 秒 | claude --print 超时限制 |
| `MAX_AI_WORKERS` | `3` | AI 并发处理线程数 |
| `MAX_OUTPUT_LEN` | `4000` 字符 | 消息最大长度（Telegram 限制） |
| `HEARTBEAT_INTERVAL` | `300` 秒 | Bot 内部心跳日志间隔 |

## 迭代方向

### 功能扩展

**1. 多用户权限控制**

在 `bot.py` 顶部添加白名单：

```python
ALLOWED_USERS = [123456789, 987654321]  # Telegram user_id

# 在 process_updates 中添加校验
user_id = msg.get("from", {}).get("id")
if user_id not in ALLOWED_USERS:
    send_message(chat_id, "⛔ 无权限", msg_id)
    continue
```

**2. 会话记忆（多轮对话）**

替换 `claude --print` 为带历史记录的调用：

```python
# 保存对话历史到文件
history_file = f"/home/vercel-sandbox/chat_{chat_id}.json"
# 构建 claude 指令时带入历史
```

**3. 定时任务支持**

新增 `/cron` 指令，让用户通过 Telegram 创建定时任务：

```
/cron add "0 9 * * *" "帮我发送早报"
/cron list
/cron delete <id>
```

**4. 文件传输**

支持 Telegram 文件上传/下载：
- 用户发送文件 → Bot 保存到沙箱
- `/download <path>` → Bot 将文件发送到 Telegram

**5. 通知推送**

Bot 主动发送通知（无需用户触发）：

```python
# 另起一个线程监听事件文件
# 有新通知时调用 send_message
```

### 性能优化

- **长轮询**：将 `getUpdates` 的 `timeout` 参数设为 30，减少无效请求
- **消息队列**：用 `queue.Queue` 替代 `ThreadPoolExecutor`，更精细控制并发
- **缓存**：对频繁查询的系统信息添加缓存，减少 subprocess 调用

### 部署优化

- **Docker 化**：将整个环境打包为 Docker 镜像
- **Webhook 模式**：替换轮询为 Webhook，减少延迟和资源消耗
- **多 Bot 支持**：支持同时运行多个 Bot Token

## 常见问题

### Bot 无响应

```bash
pm2 list                        # 检查进程状态
pm2 logs telegram-remote        # 查看错误日志
bash keepalive.sh               # 手动触发保活
```

### 锁文件导致无法启动

```bash
rm -f /home/vercel-sandbox/telegram_remote.lock
pm2 restart telegram-remote
```

### Cron 保活过期

在 Claude 会话中发送：
> 帮我续期 Telegram Bot 的保活定时任务，执行脚本是 /home/vercel-sandbox/keepalive.sh，每5分钟一次

### claude --print 超时

- 简化问题描述
- 调大 `CLAUDE_TIMEOUT` 参数
- 复杂任务拆分为多步骤

## 版本历史

| 版本 | 说明 |
|------|------|
| v1.0 | 基础 /cmd 命令执行 + Maton API |
| v1.1 | 切换为直接 Telegram Bot API |
| v1.2 | 新增 Claude AI 对话（OpenRouter → Bedrock） |
| v1.3 | 改用 claude --print 异步处理，彻底解耦 |
| v1.4 | 线程池并发 + 锁文件自动清理 + 一键部署脚本 |
