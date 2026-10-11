# Deployment Notes

## Conda

This project expects two separate conda environments:

```powershell
conda create -n we-mp-rss python=3.13
conda create -n goactivity python=3.11
```

If `conda` is not in PATH, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\locate-conda.ps1
```

If that script cannot find `conda.exe`, the `C:\Users\threeyang\.anaconda` directory is likely only Anaconda configuration/keyring data, not a full Miniconda/Anaconda installation.

## Desktop Manager (Recommended)

The PySide6 desktop manager manages both services:

```powershell
python -m desktop.app
```

This starts GoActivity (port 8000) and we-mp-rss (port 8001) automatically, with a dual-status tray icon and right-click menu for independent control.
The legacy `gui_manager.py` remains available when compatibility with the older tray entry is required.

### Auto-restart

Both services are monitored every 10 seconds. If a service crashes or becomes unresponsive (3 consecutive health check failures), the tray manager automatically restarts it with exponential backoff (5s → 10s → 20s, max 3 attempts). User-initiated stops are not affected by auto-restart.

Subprocess stdout/stderr are logged to:
- `logs/goactivity_service.log` (GoActivity)
- `logs/werss_service.log` (we-mp-rss)

Log files auto-rotate at 5 MB (old log kept as `.log.old`).

## we-mp-rss without Docker

### Prerequisites

we-mp-rss requires Playwright for browser automation (WeChat login). Install Playwright browsers after setting up the conda environment:

```powershell
conda activate we-mp-rss
playwright install chromium
```

### Setup

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-we-mp-rss.ps1
```

### Start independently (if not using tray manager)

```powershell
cd .\we-mp-rss
conda activate we-mp-rss
python main.py -job True -init True
```

Configure its WebHook target:

```text
http://localhost:8000/webhooks/we-mp-rss
```

If you create an Access Key in `we-mp-rss`, add these to GoActivity `.env`:

```env
WE_MP_RSS_ACCESS_KEY=WK...
WE_MP_RSS_SECRET_KEY=SK...
```

Then you can manually pull articles through:

```text
POST http://localhost:8000/sync/we-mp-rss/articles
```

If AK/SK is not ready, use the public RSS fallback:

```text
POST http://localhost:8000/sync/we-mp-rss/rss/all
```

Runtime inspection endpoints:

```text
GET http://localhost:8000/diagnostics/config
GET http://localhost:8000/sync/runs/latest/we-mp-rss-json
GET http://localhost:8000/sync/runs/latest/we-mp-rss-rss:all
GET http://localhost:8000/sync/runs/summary
GET http://localhost:8000/sync/logs
```

Suggested troubleshooting order:

1. `GET /health` — 增强健康检查（返回各组件状态：database, lark_cli, vision_api, we_mp_rss, last_sync）
2. `GET /diagnostics/config`
3. `GET /sync/runs/latest/{source}`
4. `GET /sync/runs/summary`
5. `GET /sync/logs`

## GoActivity

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-goactivity-conda.ps1
conda activate goactivity
copy .env.example .env
# 首次运行：初始化数据库（自动执行 Alembic 迁移）
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Database migrations

GoActivity uses Alembic for schema migrations. On startup, `init_db()` automatically runs `alembic upgrade head`. To manually manage migrations:

```powershell
# Apply pending migrations
D:\miniconda3\envs\goactivity\python.exe -m alembic upgrade head

# Generate a new migration after model changes
D:\miniconda3\envs\goactivity\python.exe -m alembic revision --autogenerate -m "description"

# Check current version
D:\miniconda3\envs\goactivity\python.exe -m alembic current
```

### OCR / Vision provider setup

Mock mode is the default and requires no credentials.

To enable OpenAI-compatible OCR and Vision:

```env
OCR_PROVIDER=openai
VISION_API_PROVIDER=openai
VISION_API_KEY=your_api_key
VISION_API_BASE_URL=https://api.openai.com/v1
VISION_API_MODEL=gpt-4.1-mini
VISION_API_TIMEOUT_SECONDS=60
```

Notes:

- `OCR_PROVIDER=openai` uses the model as image-to-text OCR.
- `VISION_API_PROVIDER=openai` uses the same compatibility endpoint for structured event extraction.
- If credentials are missing, the API returns explicit `400` errors instead of failing silently.

### Sync run endpoints

GoActivity now distinguishes between:

- process logs: `GET /sync/logs`
- aggregated log summary: `GET /sync/summary`
- task-level sync run status: `GET /sync/runs`, `GET /sync/runs/summary`, `GET /sync/runs/latest/{source}`, `GET /sync/runs/{run_id}`

Use sync runs first when you need to know whether a specific pull operation succeeded or failed.

## Automation Health Checks

自动化链路出现延迟或结果异常时，按以下顺序检查：

```text
GET  http://127.0.0.1:8000/health
GET  http://127.0.0.1:8000/automation/status
GET  http://127.0.0.1:8000/automation/accounts-health
GET  http://127.0.0.1:8000/automation/feishu-reconcile
GET  http://127.0.0.1:8000/sync/status
```

`/automation/status` 用于确认必需调度任务已注册、下一次执行时间和维护结果；`/automation/accounts-health` 从完整订阅列表计算公众号新鲜度，`never_collected` 表示尚未成功采集，不等同于公众号不存在；`/automation/feishu-reconcile` 是只读差异预览。

只有明确需要人工修复时才调用：

```text
POST http://127.0.0.1:8000/automation/feishu-reconcile
```

该接口只允许补建本地仍存在、飞书明确缺失的活跃记录。缺失比例过高、快照过期或二次读取不一致时会安全拒绝修复，避免一次异常读取造成批量重复写入。优先公众号可以通过 `POST /automation/collect-priority` 触发，接口会返回选中、尝试、成功和失败数量。
