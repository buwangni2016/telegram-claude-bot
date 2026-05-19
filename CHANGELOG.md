# CHANGELOG

所有版本的更新记录，遵循 [语义化版本](https://semver.org/lang/zh-CN/) 规范。

格式：`[X.Y.Z] - YYYY-MM-DD (branch: <分支名>)`

---

## [3.0.0] - 2026-05-19 (branch: v3-full)

### Added
- 图形化底部持久键盘（ReplyKeyboardMarkup），6 大功能分类一键直达
- 状态机交互：点按钮后直接输入内容，无需命令前缀
- 游戏娱乐模块（modules/games.py）
  - 猜数字：带快捷数字按钮，可输入任意值
  - 石头剪刀布：按钮直接出拳
  - 今日运势：基于日期固定种子 + Claude 生成签语
- 拓展工具模块（modules/tools.py）
  - 天气查询（wttr.in 免费接口）
  - IP/域名归属查询（ipapi.co）
  - 二维码生成（qrcode 库，发送图片）
  - 多语言翻译（Claude 实现）
  - 代码分析 / 角色扮演对话
  - 文件上传自动分析
- 图形界面模块（modules/ui.py）：所有键盘定义 + 用户状态机
- 定时任务管理（/cron add/list/del）
- 网站监控管理（/monitor add/list/del）
- 新成员入群自动欢迎语

### Changed
- 消息路由重构，支持状态优先处理
- 长消息自动分页逻辑优化

---

## [2.0.0] - 2026-05-19 (branch: v2-secure)

### Added
- 安全模块（modules/security.py）
  - 管理员白名单（ADMIN_IDS，支持 config 配置）
  - 用户黑名单（自动拉黑 + 持久化）
  - 完整审计日志（每条消息、每次命令均记录）
  - 高危命令拦截黑名单（rm -rf /、mkfs 等）
- 监控模块（modules/monitoring.py）
  - /status 系统状态总览
  - /mem 内存 + CPU + TOP5 进程
  - /disk 磁盘 + 自动清理缓存
  - /net 网络 + 端口 + 外网IP
  - 后台内存告警线程（超阈值自动推送管理员）
  - 后台磁盘告警线程
  - 网站监控后台线程
- /audit 查看审计日志（管理员）
- 群聊内非管理员执行 /cmd 自动拦截
- 新成员入群欢迎语

### Changed
- 命令执行结果增加审计记录
- 错误处理更完善

---

## [1.0.0] - 2026-05-19 (branch: v1-simple)

### Added
- 核心模块（modules/core.py）
  - Telegram Bot API 封装
  - 消息发送 + 自动分页
  - 多轮对话历史（每用户独立，MAX_HISTORY 条）
  - Claude CLI 调用（异步线程池）
  - 状态持久化（last_update_id）
  - 锁文件防重复启动
  - 心跳日志
- /cmd 终端命令执行（仅管理员）
- 基础高危命令过滤
- /start /help /clear 通用指令
- PM2 进程托管
- 保活机制（keepalive.sh）
- 一键部署脚本（scripts/setup_v1.sh）

---

## Bug Fix 同步规则

```
main → v1-simple → v2-secure → v3-full
```

- `modules/core.py` 的 bug 修复：提交到 main，依次 cherry-pick 到三条分支
- `modules/security.py` / `monitoring.py` 的修复：提交到 v2-secure，cherry-pick 到 v3-full
- v3-full 特有模块的修复：仅在 v3-full 提交

### 版本号约定
- **X（主版本）**：功能层级变更（v1→v2→v3）
- **Y（次版本）**：新增功能（不破坏现有功能）
- **Z（补丁版本）**：bug 修复、性能优化
