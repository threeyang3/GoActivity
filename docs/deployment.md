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

## Tray Manager (Recommended)

The system tray application (`gui_manager.py`) manages both services:

```powershell
python gui_manager.py
```

This starts GoActivity (port 8000) and we-mp-rss (port 8001) automatically, with a dual-status tray icon and right-click menu for independent control.

## we-mp-rss without Docker

Setup:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-we-mp-rss.ps1
```

Start independently (if not using tray manager):

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
