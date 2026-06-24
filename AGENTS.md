# Repository Guidelines

## Project Overview
This repository is the working root for the Campus Activity Knowledge Hub project.

There are two cooperating services:

1. `we-mp-rss/`
   Collects and exports WeChat public account articles.
2. `app/`
   GoActivity FastAPI service that ingests articles, stores markdown and images, runs OCR/Vision extraction, and syncs events into Feishu Bitable.

The end-to-end flow currently verified on this machine is:

`we-mp-rss -> GoActivity -> image preservation -> OCR/Vision extraction -> Feishu Bitable -> daily report`

## Current Local Status
The current Windows machine has already been configured and verified.

- Workspace root: `E:\cctry\GoActivity`
- Miniconda root: `D:\miniconda3`
- `goactivity` env: Python `3.11`
- `we-mp-rss` env: Python `3.13`
- GoActivity service: `http://127.0.0.1:8000`
- we-mp-rss service: `http://127.0.0.1:8001`
- Feishu sync path: `lark-cli`
- Feishu target Base: `Campus Activity Knowledge Hub`
- Feishu target table: `活动库`
- Feishu attachment field for posters: `海报附件`

As of the latest verified run (2026-06-20):

- all local `Event` rows are synced to Feishu
- poster images are uploaded as real Feishu attachments
- `event.feishu_record_id` is persisted locally and reused on update
- Alembic migration system is active (4 migrations)
- 144 tests passing
- Event deduplication via `dedup_key` field

## Project Structure
- `app/`
  FastAPI application code.
- `app/routes/`
  APIRouter modules: `health.py`, `events.py`, `sync.py`, `reports.py`, `setup.py`, `webhooks.py`, `articles.py`, `dashboard.py`.
- `app/services/`
  Business logic for ingestion, image processing, extraction, Feishu sync, reports, diagnostics, auto-sync, scheduling, Feishu messaging, view setup, bot handler, bot consumer, extraction validator.
- `app/services/feishu_fields.py`
  Feishu Bitable field building logic: `build_record_fields`, `SELECT_OPTIONS`, type conversion helpers.
- `app/services/extraction_validator.py`
  Post-extraction validation: category, confidence, time range, required fields.
- `app/exceptions.py`
  Unified exception hierarchy: `AppError` → `ProviderError`, `FeishuError`, `SyncError`, `ValidationError`.
- `app/logging_config.py`
  Structured logging setup (JSON or readable format).
- `app/utils/`
  Shared utilities: `time.py` (utcnow, parse_datetime_str, parse_to_epoch), `constants.py` (EventStatus, RetentionDecision, EventTimeStatus, ACTIVITY_KIND_LABELS), `lark_cli.py` (lark-cli command building, run_cli_command), `ids.py`, `jsonx.py`, `cron.py` (shared `parse_cron`).
- `app/static/`
  Static files for Web management UI. `index.html` is the dashboard.
- `alembic/`
  Alembic migration system. Run `alembic upgrade head` to apply pending migrations.
- `storage/`
  Local runtime data for GoActivity.
- `storage/app.db`
  SQLite database for GoActivity (WAL mode enabled).
- `storage/articles/`
  Saved markdown/article artifacts.
- `storage/images/`
  Downloaded article and poster images.
- `scripts/`
  Management scripts for we-mp-rss (start/stop/status/install-task) and GoActivity setup.
- `tests/`
  Pytest suite (144 tests). `conftest.py` uses set-difference cleanup: records existing IDs before each test, deletes only new ones after.
- `.github/workflows/ci.yml`
  CI pipeline: pytest on push/PR to main.
- `we-mp-rss/`
  Upstream article collection service. See its own `AGENTS.md` for repo-specific details.

## Environment and Secrets
Local runtime configuration is in `.env`. Do not commit real secrets.

Important values already used by the running project include:

- `WE_MP_RSS_ACCESS_KEY`
- `WE_MP_RSS_SECRET_KEY`
- `FEISHU_PROVIDER=lark_cli`
- `FEISHU_CLI_PATH`
- `FEISHU_CLI_AS=user`
- `FEISHU_BITABLE_APP_TOKEN`
- `FEISHU_BITABLE_TABLE_ID`
- `FEISHU_POSTER_ATTACHMENT_FIELD=海报附件`
- `FEISHU_REPORT_CHAT_ID` — 日报/周报发送的目标群 ID（oc_xxx）
- `FEISHU_REPORT_USER_ID` — 日报/周报发送的目标用户 ID（ou_xxx），与 CHAT_ID 二选一
- `FEISHU_REPORT_DAILY_CRON` — 日报定时发送 cron 表达式（默认每天 9:00）
- `FEISHU_REPORT_WEEKLY_CRON` — 周报定时发送 cron 表达式（默认每周一 9:00）
- `FEISHU_REPORT_DAILY_ENABLED` — 启用/禁用日报定时发送（默认 true）
- `FEISHU_REPORT_WEEKLY_ENABLED` — 启用/禁用周报定时发送（默认 true）
- `OCR_PROVIDER` — OCR 提供商（mock / openai）
- `VISION_API_PROVIDER` — Vision 提供商（mock / openai）
- `VISION_API_KEY` — Vision API 密钥
- `VISION_API_BASE_URL` — Vision API 地址（智谱 AI: `https://open.bigmodel.cn/api/paas/v4`）
- `VISION_API_MODEL` — Vision 模型（智谱 AI: `glm-4.6v`）
- `VISION_API_TIMEOUT_SECONDS` — Vision API 超时（默认 60）
- `AUTO_SYNC_CRON` — 自动同步 cron 表达式（默认 `0 * * * *`，每小时）
- `FEISHU_BOT_ENABLED` — 启用/禁用飞书机器人（默认 false）
- `FEISHU_BOT_APP_ID` — 飞书应用 App ID（bot 需要）
- `FEISHU_BOT_RATE_LIMIT` — 机器人每用户每分钟消息上限（默认 10）

Never print or commit secret values in docs, tests, or logs.

## Run Commands
Use the dedicated conda envs instead of relying on global PATH.

GoActivity:

```powershell
D:\miniconda3\envs\goactivity\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

we-mp-rss:

```powershell
D:\miniconda3\envs\we-mp-rss\python.exe main.py -job True -init True
```

Tests:

```powershell
D:\miniconda3\envs\goactivity\python.exe -m pytest -q
```

Alembic migrations:

```powershell
D:\miniconda3\envs\goactivity\python.exe -m alembic upgrade head
D:\miniconda3\envs\goactivity\python.exe -m alembic revision --autogenerate -m "description"
```

## Feishu Sync Notes
The preferred integration is `lark-cli`, not the older `feishu` CLI.

Important implementation details:

- Do not call `lark-cli.cmd` directly for write operations with large JSON payloads.
- On Windows, the code resolves `lark-cli.cmd` to `node.exe + run.js` to avoid command-line quoting issues.
- `is_lark_cli()` recognizes `lark-cli`, `lark-cli.exe`, and `lark-cli.cmd`.
- Subprocess output must be read as UTF-8, or Node CLI output may break under Windows default code pages.
- `lark-cli base +record-upsert` is not true business-key upsert:
  - without `--record-id`, it creates
  - with `--record-id`, it updates
- Poster attachments are uploaded after record write through `+record-upload-attachment`.
- `lark-cli` only accepts safe relative file paths for attachment upload; absolute paths will fail.
- `FeishuOpenAPIClient` also supports poster attachment upload via `/open-apis/drive/v1/medias/upload_all`.

## Feishu Bot
The Feishu bot uses `lark-cli event consume im.message.receive_v1 --as bot` to receive messages via long connection (no public callback URL needed).

Key implementation details:
- `BotEventConsumer` runs `lark-cli event consume` as a subprocess in a daemon thread
- The subprocess stdin must be kept open (`stdin=subprocess.PIPE`) or it exits immediately on EOF
- `lark-cli event consume` outputs NDJSON to stdout (one JSON object per line, data at top level, not nested under `event`)
- Bot replies use `lark-cli im +messages-reply --as bot --message-id <id> --markdown <content>`
- `BotHandler` uses the configured Vision API (GLM-4.6V) as an LLM for natural language understanding
- Rate limiting: per-user, per-minute (configurable via `FEISHU_BOT_RATE_LIMIT`, default 10)
- Conversation history: last 5 turns per user, stored in class-level shared state with thread lock
- Image messages: returns placeholder response (image recognition TBD)
- Required Feishu app permissions: `im:message.p2p_msg:readonly`, `im:message:send_as_bot`
- Required event subscription: `im.message.receive_v1` (长连接模式)

## Image Filtering
Decorative images (icons, separators, QR codes) are automatically filtered out.

Filter rules in `app/services/image_service.py`:
- File size < 50KB (`_MIN_FILE_SIZE`)
- Width or height < 80px (`_MIN_DIMENSION`)
- Area < 80×80 (`_MIN_AREA`)
- Aspect ratio > 15:1 (`_MAX_ASPECT_RATIO` — separator lines)

Filtering happens at two levels:
1. **Download time** (`_is_too_small`): marks as `filtered_decorative`, not added to image_map
2. **Selection time** (`_is_decorative`): excluded from `select_key_images` poster candidates

To re-filter existing Feishu Bitable records:
```
POST /events/refilter-images
```
This re-evaluates poster_images for all synced events, removes decorative images, and re-syncs to Feishu.

## Auto-Sync Flow
Each hourly sync run executes these steps in order:
1. Fetch new articles from we-mp-rss
2. Retry failed image downloads (`needs_image_retry` events)
3. Refresh event statuses (re-evaluate `event_time_status` for all synced events: `upcoming` → `past`)
4. Sync new events to Feishu Bitable

## Alembic Migrations
The project uses Alembic for database schema migrations.

- `alembic.ini` at project root
- `alembic/env.py` imports app models and overrides URL from `app.config`
- `render_as_batch=True` for SQLite ALTER TABLE support
- `init_db()` calls `create_all()` then `alembic upgrade head`
- Fresh databases get `alembic stamp head` automatically

Current migration chain:
1. `b3b280a6e3b8` — initial schema (NOT NULL constraint alignment)
2. `7701d0eef212` — add `events.dedup_key`
3. `3b6e4c04bbee` — add `sync_logs.run_id`
4. `a1b2c3d4e5f6` — add indexes on `events.status`, `events.start_time`, `events.feishu_record_id`

## Coding Rules for This Repo
- Use `apply_patch` for manual file edits.
- Avoid broad refactors unless explicitly requested.
- Preserve the current dual-service architecture.
- Keep SQLite-compatible behavior unless a migration is explicitly requested.
- Prefer extending existing services over introducing parallel implementations.
- For Feishu sync changes, preserve both:
  - text fields for event metadata
  - attachment upload for poster images
- Use `app/exceptions.py` hierarchy (`ProviderError`, `FeishuError`, `SyncError`, `ValidationError`) instead of raw `RuntimeError`.
- Use `app/utils/cron.py::parse_cron` for cron parsing (shared between auto_sync and scheduler).
- Routes live in `app/routes/`, not in `main.py`. Only state-dependent routes (`/bot/status`, `/sync/auto`) stay in `main.py`.
- Use `app/utils/time.py::utcnow()` instead of `datetime.utcnow()` (deprecated).

## Validation Expectations
For meaningful changes, prefer real verification, not only unit tests.

Useful checks:

```text
GET  /health
GET  /diagnostics/config
POST /sync/we-mp-rss/articles
POST /sync/auto                  # 触发一次完整同步（拉取+抽取+飞书）
POST /events/{event_id}/extract
POST /events/{event_id}/sync-feishu
POST /setup/feishu-views         # 创建/更新飞书视图（幂等）
POST /reports/daily?send_to_feishu=true
POST /reports/weekly?send_to_feishu=true
GET  /sync/logs
GET  /sync/runs/latest/we-mp-rss-json
GET  /bot/status
```

If touching Feishu sync, verify both:

1. local DB state updates correctly
2. Feishu Bitable record or attachment changes actually appear

## Known Operational Pitfalls
- `we-mp-rss` browser session can expire in the UI while its backend API is still usable.
- The app browser may show a stale login redirect even when the backend service is healthy.
- Background Windows processes may not inherit the same PATH as an interactive PowerShell session.
- If `lark-cli` works in terminal but fails in the service, check executable resolution first.
- If Feishu write succeeds locally but not via HTTP, restart the live `uvicorn` process to ensure it picked up new code.
- APScheduler is pinned to `<4.0.0` (4.x has breaking API changes).

## Handoff Notes
When continuing work, assume the following are already true unless a later failure shows otherwise:

- `we-mp-rss` subscription and authorization were previously completed
- real articles from `北大团委`, `北京大学百周年纪念讲堂`, `北京大学人文社会科学研究院`, `北京大学人文学部` have been ingested
- all current events have already been synced to Feishu once
- Vision API (智谱 AI GLM-4.6V) is configured and working
- automatic sync service is running (hourly cron)
- 13 Feishu views are created with proper filters (excluding past/expired/recap)
- daily/weekly reports are sent to user's Feishu via `FEISHU_REPORT_USER_ID`
- Alembic migrations are up to date (4 migrations applied)
- 144 tests passing, CI pipeline configured
- Web management UI available at `http://localhost:8000/`
- SQLite WAL mode enabled for better concurrent read/write performance
- New accounts can be added following `docs/adding-accounts.md`

If you need repository-specific guidance for the collector service itself, also read:

- [we-mp-rss/AGENTS.md](E:/cctry/GoActivity/we-mp-rss/AGENTS.md)
