# 配置指南

## 配置概览

GoActivity 使用三层配置：

1. **默认值** — 代码中的默认配置
2. **.env 文件** — 启动时加载
3. **运行时设置** — 通过管理页面 API 修改，持久化到 `app_settings` 与密钥文件

## Provider 说明

### OCR Provider

负责从图片中提取文字。

| Provider | 说明 | 需要 API Key |
|----------|------|-------------|
| mock | 测试模式，返回占位文本 | 否 |
| disabled | 禁用 OCR | 否 |
| rapid | 本地 RapidOCR（免费、离线） | 否 |
| openai_compatible | OpenAI 兼容 API | 是 |

使用 `rapid` 时，首次部署需要额外安装：

```bash
pip install -r requirements-ocr.txt
```

### Vision Provider

多模态分析，同时使用图片和文字。

| Provider | 说明 | 需要 API Key |
|----------|------|-------------|
| mock | 测试模式 | 否 |
| openai_compatible | 多模态 API（如 GPT-4V） | 是 |
| textai | 兼容旧配置值，会路由到文本 AI 管线 | 是 |

### 文本 AI Provider

纯文本分析，不处理图片。

| Provider | 说明 | 需要 API Key |
|----------|------|-------------|
| disabled | 禁用 | 否 |
| mock | 测试模式 | 否 |
| openai_compatible | OpenAI 兼容 API | 是 |

## 推荐管线

1. **本地 RapidOCR + 多模态 Vision** — 适合有 GPU 的环境
2. **API OCR + 多模态 Vision** — 适合需要高精度的场景
3. **本地 RapidOCR + 文本 AI** — 成本最低，适合大量处理

## 热加载 vs 需要重启

### 可热加载（立即生效）

- OCR/Vision/文本 AI Provider 配置
- API Base URL、模型、超时
- 飞书 Provider 参数
- 报告收件人
- 自动归档天数

### 需要重建任务

- 自动同步 Cron
- 日报/周报 Cron 和开关
- 优先公众号采集 Cron
- 飞书对账 Cron 和开关

### 需要重启

- 服务端口
- 监听地址
- 数据库地址
- 存储目录

## 密钥安全

- 密钥不写入普通设置表，当前默认保存在 `storage/settings.secrets.json`
- API 返回密钥时使用掩码（如 `sk-****abcd`）
- 日志中不记录密钥
- 修改 `storage_dir` 并同时更新密钥时，密钥文件会写入新的存储目录，避免热加载后丢失配置

## WeRSS Webhook

- 同机 `127.0.0.1` 推送保持免令牌，适用于默认双服务部署
- 跨机器推送必须配置 `WE_MP_RSS_WEBHOOK_TOKEN`
- 发送方通过 `X-GoActivity-Webhook-Token` 请求头传递令牌
- 未配置令牌时，远程 Webhook 返回 `503`；令牌错误返回 `401`

## 自动化守护

| 配置 | 默认值 | 用途 |
|------|--------|------|
| `FEISHU_SYNC_RETRY_MAX` | `6` | 单条飞书失败同步最大自动重试次数 |
| `FEISHU_SYNC_RETRY_BASE_MINUTES` | `15` | 指数退避基数，实际间隔为 15/30/60... 分钟，最长 24 小时 |
| `PRIORITY_ACCOUNTS` | 空 | 逗号分隔的高优先级公众号名称；空值表示全部订阅 |
| `PRIORITY_COLLECTION_CRON` | `*/30 * * * *` | 高频采集触发周期；成功后 2 分钟接续完整同步 |
| `AUTO_SYNC_STALE_MINUTES` | `180` | 自动同步超过该延迟仍未完成时，健康检查标记为 degraded |
| `FEISHU_RECONCILE_MAX_MISSING_RATIO` | `0.2` | 人工对账修复允许的最大缺失比例；定时对账始终只读检测 |
| `FEISHU_RECONCILE_SNAPSHOT_HOURS` | `24` | 对账稳定快照的最长确认有效期 |
| `ACCOUNT_STALE_HOURS` | `36` | 公众号最后一次发文/入库超过该时长时标记 SLA 异常 |
| `FEISHU_RECONCILE_ENABLED` | `true` | 是否启用每日 Base 对账 |
| `FEISHU_RECONCILE_CRON` | `30 3 * * *` | 飞书对账周期 |
| `AUTOMATION_ALERTS_ENABLED` | `true` | 是否向报告收件人发送链路告警 |
| `AUTOMATION_ALERT_COOLDOWN_HOURS` | `6` | 同类告警冷却时间 |

对账默认只读。定时任务和管理页“修复缺失”只会重建本地存在、飞书记录已明确缺失的活跃数据；隐藏、过滤或归档等终态活动会被跳过。字段漂移与附件缺失只展示并告警，避免自动覆盖人工维护内容。

修改自动化配置后，可通过 `GET /automation/status` 检查调度任务是否已注册、下一次执行时间、同步延迟和维护结果；通过 `GET /automation/feishu-reconcile` 查看只读对账预览。不要把“任务已注册”误认为“本次任务已成功”，具体结果应同时查看 `last_sync`、维护结果和 `GET /sync/runs`。

## 局域网访问

默认仅监听 127.0.0.1。启用局域网访问：

1. 在设置页面开启 `allow_lan_access`
2. 配置 `admin_token`
3. 重启服务

局域网访问时，所有写接口需要 Bearer token 认证。
