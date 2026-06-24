# Campus Activity Knowledge Hub

校园活动知识库服务。`we-mp-rss` 负责公众号采集，GoActivity 负责文章接收、图片保真、OCR/多模态抽取、本地活动库和飞书同步。

## 本地环境

推荐使用两个独立 conda 环境：

```powershell
conda create -n we-mp-rss python=3.13
conda create -n goactivity python=3.11
conda activate goactivity
pip install -r requirements.txt
```

初始化数据库（首次运行自动执行 Alembic 迁移）：

```powershell
D:\miniconda3\envs\goactivity\python.exe -m alembic upgrade head
```

当前机器如果 `conda` 不在 PATH，请先从 Anaconda/Miniconda 安装目录初始化 PowerShell，或使用 Anaconda Prompt。

Miniconda 路径（当前机器）：`D:\miniconda3`

## 自动检测推文链路

```
微信公众号 → we-mp-rss（采集） → GoActivity（处理） → 飞书多维表格
```

| 步骤 | 组件 | 机制 | 频率 |
|------|------|------|------|
| ① 监控公众号 | we-mp-rss | 后台定时抓取已订阅的公众号 | 取决于 we-mp-rss 配置 |
| ② 拉取新文章 | GoActivity → we-mp-rss | `AutoSyncService` 主动拉取 | 每小时（`AUTO_SYNC_CRON`） |
| ③ AI 抽取 | GoActivity | Vision API 提取活动信息 | 随拉取触发 |
| ④ 同步飞书 | GoActivity → 飞书 | lark-cli 写入多维表格 | 随抽取触发 |
| ⑤ 日报/周报 | GoActivity → 飞书 | `ReportScheduler` 发送 | 每天 9:00 / 每周一 9:00 |

### 一键启动（手动）

```powershell
# 终端 1：启动 we-mp-rss
cd E:\cctry\GoActivity\we-mp-rss
D:\miniconda3\envs\we-mp-rss\python.exe main.py -job True -init True

# 终端 2：启动 GoActivity
cd E:\cctry\GoActivity
D:\miniconda3\envs\goactivity\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

健康检查：

```text
GET http://localhost:8000/health
```

### 开机自启（Windows 计划任务）

用管理员 PowerShell 运行 `scripts/install-autostart.ps1`，会创建两个计划任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-autostart.ps1
```

创建的任务：
- `GoActivity` — 登录时启动 GoActivity（端口 8000）
- `WeMpRss` — 登录时启动 we-mp-rss（端口 8001）

管理命令：

```powershell
schtasks /Query /TN "GoActivity"    # 查看状态
schtasks /Run /TN "GoActivity"      # 手动启动
schtasks /End /TN "GoActivity"      # 停止
schtasks /Delete /TN "GoActivity"   # 删除
```

### 推送模式（可选）

默认使用**拉模式**（GoActivity 每小时主动拉取）。如果想要新文章秒级触达，可在 we-mp-rss 中配置 webhook：

1. 访问 `http://localhost:8001` → 消息任务 → 新建
2. webhook 地址：`http://localhost:8000/webhooks/we-mp-rss`
3. 格式选 JSON

### 飞书机器人（AI 对话查询）

GoActivity 内置飞书机器人，支持自然语言查询活动。接入智谱 AI GLM-4.6V，可以问"有什么推荐活动？"、"这周末有啥讲座？"等。

**启用步骤：**

1. 在飞书开发者后台（https://open.feishu.cn/app）为应用添加**机器人**能力
2. 添加权限：`im:message`、`im:message.p2p_msg:readonly`、`im:message:send_as_bot`
3. 事件订阅：添加 `im.message.receive_v1`，选择**长连接接收事件**
4. 发布应用版本
5. 配置 `.env`：

```env
FEISHU_BOT_ENABLED=true
FEISHU_BOT_APP_ID=cli_xxx
```

6. 重启 GoActivity，在飞书中给机器人发消息测试

**支持的对话示例：**
- "这周末有什么活动？"
- "推荐几个讲座"
- "有没有志愿者招募？"
- "7月有什么演出？"
- "帮我找一下关于AI的活动"

检查机器人状态：`GET http://localhost:8000/bot/status`

## 部署 we-mp-rss（无 Docker）

`we-mp-rss` 已包含在项目的 `we-mp-rss/` 目录中，无需单独 clone：

```powershell
cd we-mp-rss
conda activate we-mp-rss
pip install -r requirements.txt
copy config.example.yaml config.yaml
python main.py -job True -init True
```

启动后访问：

```text
http://localhost:8001
```

在 `we-mp-rss` 中订阅目标公众号后，GoActivity 会自动拉取新文章。

内容格式优先选 Markdown；如果只能输出 HTML/JSON，GoActivity 的 adapter 会做字段归一化。

## V1 能力

- 接收 `we-mp-rss` WebHook。
- 保存原始 payload、Markdown、处理后 Markdown。
- 下载 Markdown/HTML 中的图片并改写本地路径。
- 支持 `mock` 和 `openai` 两类 OCR/Vision provider（已配置智谱 AI GLM-4.6V）。
- 通过 `FeishuAdapter` 调用 `lark-cli`、兼容飞书 CLI 或飞书 OpenAPI；默认 `FEISHU_DRY_RUN=true`，不会真实写飞书。
- 提供配置自检、同步日志、同步任务状态接口，便于排障。
- 提供结构化日报/周报（按时间筛选、分类统计、活动列表），支持发送到飞书群/用户。
- 自动同步服务：定时从 we-mp-rss 拉取新文章、Vision 抽取、同步到飞书（每小时）。
- 飞书视图自动创建/更新（13 个视图，支持过滤、排序、分组）。
- 事件去重：基于标题+时间+地点的 SHA-256 去重键，避免同一活动重复入库。
- 抽取后校验：自动修正非法分类、超范围置信度、不合理时间。
- 图片过滤：自动排除装饰性图片（<50KB、<80px、极端比例），只保留有效海报图。
- 事件状态自动刷新：每小时重新评估已同步事件的时间状态（upcoming → past），自动更新飞书。
- Alembic 数据库迁移系统，支持 schema 版本管理。
- 统一异常体系（ProviderError/FeishuError/SyncError/ValidationError）。
- 增强健康检查（DB、lark-cli、Vision API、we-mp-rss、上次同步状态）。
- 飞书机器人：自然语言查询、速率限制、对话历史。
- CI pipeline（GitHub Actions：pytest + import check）。
- Web 管理后台：统计仪表板、事件列表、同步日志、快捷操作、活动详情、搜索、时间筛选、待办事项。
- SQLite WAL 模式：提升并发读写性能。
- 数据库索引：`status`、`start_time`、`feishu_record_id` 字段索引。
- 公众号添加指南：`docs/adding-accounts.md`。

## 主要接口

- `GET /` — 重定向到 Web 管理后台
- `GET /health` — 增强健康检查（DB、lark-cli、Vision API、we-mp-rss、上次同步状态）
- `GET /bot/status` — 飞书机器人运行状态
- `GET /diagnostics/config`
- `POST /webhooks/we-mp-rss`
- `POST /sync/we-mp-rss/articles`
- `POST /sync/we-mp-rss/rss/{feed_id}`
- `POST /sync/auto` — 手动触发一次完整同步（拉取+抽取+飞书）
- `GET /sync/logs`
- `GET /sync/summary`
- `GET /sync/runs`
- `GET /sync/runs/summary`
- `GET /sync/runs/latest/{source}`
- `GET /sync/runs/{run_id}`
- `GET /events` — 事件列表（支持分页：`page`、`page_size`、`status`）
- `POST /articles/{article_id}/process-images`
- `POST /events/{event_id}/extract`
- `POST /events/{event_id}/sync-feishu`
- `POST /events/{event_id}/keep` — 置顶/取消置顶活动
- `POST /events/cleanup-expired` — 批量清理过期活动
- `POST /events/refilter-images` — 重新过滤所有已同步事件的海报图片（排除装饰性图片，更新飞书附件）
- `POST /setup/feishu-views` — 创建/更新飞书视图（幂等）
- `POST /reports/daily?send_to_feishu=true`
- `POST /reports/weekly?send_to_feishu=true`
- `GET /dashboard/stats` — 仪表板统计数据
- `GET /dashboard/events` — 仪表板事件列表（分页、筛选、时间范围）
- `GET /dashboard/events/{event_id}` — 活动详情
- `GET /dashboard/search?q=xxx` — 搜索活动
- `GET /dashboard/today` — 今日活动和即将到来的活动
- `GET /dashboard/pending` — 待办事项（低置信度、同步失败、待同步、图片重试）
- `GET /dashboard/accuracy` — 抽取准确率统计
- `GET /dashboard/sync-logs` — 仪表板同步日志
- `GET /dashboard/sync-runs` — 仪表板同步运行记录
- `GET /dashboard/feishu-link` — 飞书多维表格链接配置

## 真实接入配置

### we-mp-rss JSON API

如果要从 `we-mp-rss` 的受保护 JSON API 拉文章，在 `.env` 中设置：

```env
WE_MP_RSS_ACCESS_KEY=WK...
WE_MP_RSS_SECRET_KEY=SK...
```

然后调用：

```text
POST /sync/we-mp-rss/articles
```

如果暂时没有 AK/SK，可以走公开 RSS 兜底：

```text
POST /sync/we-mp-rss/rss/all
POST /sync/we-mp-rss/rss/{feed_id}
```

如果要检查为什么 JSON 同步没工作，优先看：

```text
GET /diagnostics/config
GET /sync/runs/latest/we-mp-rss-json
GET /sync/logs?target=feishu_event
```

### OpenAI 兼容 OCR / Vision

如果要启用真实模型，在 `.env` 中设置：

```env
OCR_PROVIDER=openai
VISION_API_PROVIDER=openai
VISION_API_KEY=your_api_key
VISION_API_BASE_URL=https://api.openai.com/v1
VISION_API_MODEL=gpt-4.1-mini
VISION_API_TIMEOUT_SECONDS=60
```

当前实现使用 OpenAI 兼容 `chat/completions`：

- OCR provider 读取图片并返回纯文本
- Vision provider 返回结构化 JSON

### 飞书同步

当前实现支持三种飞书接入方式：

- `FEISHU_PROVIDER=lark_cli`
  - 优先推荐，直接调用 `lark-cli base +record-upsert`
  - 需要本机可执行 `lark-cli`
  - 需要配置 `FEISHU_CLI_AS`、`FEISHU_BITABLE_APP_TOKEN` 和 `FEISHU_BITABLE_TABLE_ID`

- `FEISHU_PROVIDER=cli`
  - 兼容原来的 CLI 子进程方案
  - 要求本机存在可执行的 `feishu` 命令，或通过 `FEISHU_CLI_PATH` 指向实际路径
- `FEISHU_PROVIDER=openapi`
  - 直接调用飞书 OpenAPI，不依赖本机 CLI
  - 更适合当前这台机器
- `FEISHU_PROVIDER=auto`
  - 如果 `FEISHU_CLI_PATH=lark-cli` 且配置了多维表格 token/table id，优先走 `lark-cli`
  - 否则如果同时配置了飞书应用凭证和多维表格信息，走 OpenAPI
  - 最后回退到旧 CLI

如果要启用基于 `lark-cli` 的真实多维表格写入，在 `.env` 中设置：

```env
FEISHU_PROVIDER=lark_cli
FEISHU_CLI_PATH=lark-cli
FEISHU_CLI_AS=user
FEISHU_DRY_RUN=false
FEISHU_BITABLE_APP_TOKEN=base_xxx
FEISHU_BITABLE_TABLE_ID=tbl_xxx
```

字段说明：

- `FEISHU_CLI_AS`
  - `lark-cli` 写入时使用的身份，当前建议 `user`
- `FEISHU_BITABLE_APP_TOKEN`
  - 多维表格的 `base_token`
- `FEISHU_BITABLE_TABLE_ID`
  - 来自目标数据表的 `table_id`

建议配置完成后按顺序验证：

```text
GET /diagnostics/config
POST /events/{event_id}/sync-feishu
GET /sync/logs?target=feishu_event
```

## 排障顺序

建议按这个顺序排障：

1. `GET /diagnostics/config`
2. `GET /sync/runs/latest/we-mp-rss-json`
3. `GET /sync/runs/latest/we-mp-rss-rss:all`
4. `GET /sync/summary`
5. `GET /sync/logs`

各接口职责：

- `GET /diagnostics/config`
  - 看配置是否缺失
- `GET /sync/runs/latest/{source}`
  - 看某个来源最近一次同步任务是否成功
- `GET /sync/runs/{run_id}`
  - 看单次任务详情
- `GET /sync/summary`
  - 看日志级的聚合失败情况
- `GET /sync/logs`
  - 看具体命令、返回码、stdout/stderr 片段
