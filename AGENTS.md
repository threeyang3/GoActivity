# Repository Guidelines

## Project Overview
This repository is the working root for the Campus Activity Knowledge Hub project.

There are two cooperating services, both managed by the system tray application (`gui_manager.py`):

1. `we-mp-rss/`
   Collects and exports WeChat public account articles (port 8001).
2. `app/`
   GoActivity FastAPI service that ingests articles, stores markdown and images, runs OCR/Vision extraction, and syncs events into Feishu Bitable (port 8000).

The tray application (`gui_manager.py`) provides:
- Start/stop/restart for both services
- Independent autostart (Windows registry) for each service
- Dual-status tray icon (green/red dots for each service)
- Unified status window showing both services' health

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

As of the latest verified run (2026-06-25):

- all local `Event` rows are synced to Feishu
- poster images are uploaded as real Feishu attachments
- `event.feishu_record_id` is persisted locally and reused on update
- Alembic migration system is active (6 migrations in repository, including runtime settings and canonical time fields)
- 189 tests passing
- Event deduplication via `dedup_key` field

## Project Structure
- `app/`
  FastAPI application code.
- `app/routes/`
  APIRouter modules: `health.py`, `events.py`, `sync.py`, `reports.py`, `setup.py`, `webhooks.py`, `articles.py`, `dashboard.py`, `accounts.py`.
- `app/services/`
  Business logic for ingestion, image processing, extraction, Feishu sync, reports, diagnostics, auto-sync, scheduling, Feishu messaging, view setup, bot handler, bot consumer, extraction validator, archive service.
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
  Static files for Web management UI. Current dashboard uses split `css/` + `js/` ES modules.
- `desktop/`
  Current PySide6 desktop manager entry (`python -m desktop.app`) plus service controller and single-instance logic.
- `gui_manager.py`
  Legacy tray manager, retained for compatibility but no longer the preferred entry.
- `generate_icon.py`
  Generates `app_icon.ico` with dual status indicators. Run `python generate_icon.py` to regenerate.
- `start_service.py`
  GoActivity service launcher (used by tray and command line).
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
  Pytest suite (162 tests). `conftest.py` uses set-difference cleanup: records existing IDs before each test, deletes only new ones after.
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
- `OCR_PROVIDER` — OCR 提供商（mock / disabled / rapid / openai）
- `VISION_API_PROVIDER` — Vision 提供商（mock / openai / textai）
- `VISION_API_KEY` — Vision API 密钥
- `VISION_API_BASE_URL` — Vision API 地址（智谱 AI: `https://open.bigmodel.cn/api/paas/v4`）
- `VISION_API_MODEL` — Vision 模型（智谱 AI: `glm-4.6v`）
- `VISION_API_TIMEOUT_SECONDS` — Vision API 超时（默认 60）
- `AUTO_SYNC_CRON` — 自动同步 cron 表达式（默认 `0 * * * *`，每小时）
- `AUTO_ARCHIVE_EXPIRED_DAYS` — 过期活动自动归档天数（默认 30，0 禁用）
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
- File size < 10KB (`_MIN_FILE_SIZE`) — only checked for small images
- Width or height < 80px (`_MIN_DIMENSION`)
- Area < 80×80 (`_MIN_AREA`)
- Aspect ratio > 15:1 (`_MAX_ASPECT_RATIO` — separator lines)
- **Poster exception**: images ≥200×200px skip file size check (微信海报压缩后可能很小)

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
1. **Fetch candidates** (`fetch_candidates`): paginate we-mp-rss API, dedup against local DB, enrich missing content (fast, HTTP only)
2. **Dry spell detection**: if no candidates AND no new articles in last 24h, trigger we-mp-rss collection and re-fetch (最多等10分钟)
3. **Parallel ingest** (`ingest_candidates_parallel`): download images (5 workers) → OCR (5 workers, skipped if no images) → Vision API (skipped if no images + short content) → DB commit (4 workers, SQLite lock retry)
4. Retry failed image downloads (`needs_image_retry` events)
5. **Parallel status refresh** (`_refresh_event_statuses`): re-evaluate `event_time_status` for all synced events; changed ones synced to Feishu in parallel (2 workers)
6. **Parallel Feishu sync** (`_sync_event_ids_parallel`): new events synced to Feishu Bitable in parallel (3 workers, per-thread SessionLocal + FeishuAdapter)
7. **Auto-archive expired** (`auto_archive_expired`): events expired > N days archived automatically (skips `user_keep`/`user_participate`), configurable via `AUTO_ARCHIVE_EXPIRED_DAYS`

Steps 4 and 5 use `ThreadPoolExecutor` with per-thread DB sessions, following the same thread-safety pattern as step 2. SQLite "database is locked" retries are handled automatically.

Phase tracking: `GET /sync/status` returns `{running, phase, message}` where phase = `fetching | extracting | syncing | done | error`.

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
5. `c2d3e4f5a6b7` — add `events.user_participate`, `events.archived_at`

## Coding Rules for This Repo
- Use `apply_patch` for manual file edits.
- Avoid broad refactors unless explicitly requested.
- Preserve the current dual-service architecture.
- Keep SQLite-compatible behavior unless a migration is explicitly requested.
- Parallel implementations (ThreadPoolExecutor) are used for I/O-bound operations (image download, OCR, article ingestion). Each worker must use independent `SessionLocal()` for SQLite thread safety.
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
POST /sync/auto                  # 触发一次完整同步（非阻塞，后台执行）
GET  /sync/status                # 查询当前同步状态（配合前端轮询）
POST /events/{event_id}/extract
POST /events/{event_id}/sync-feishu
POST /setup/feishu-views         # 创建/更新飞书视图（幂等）
POST /reports/daily?send_to_feishu=true
POST /reports/weekly?send_to_feishu=true
GET  /sync/logs
GET  /sync/runs/latest/we-mp-rss-json
GET  /bot/status
GET  /accounts                    # 列出已订阅公众号
GET  /accounts/search/{kw}        # 搜索公众号
POST /accounts                    # 添加公众号
DELETE /accounts/{mp_id}          # 删除公众号
POST /accounts/update/{mp_id}     # 触发公众号文章更新
POST /events/{event_id}/participate  # 标记/取消参与
POST /events/{event_id}/archive      # 手动归档
POST /events/{event_id}/unarchive    # 取消归档
GET  /dashboard/pipeline-status      # 数据管道状态
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
- **Python 3.14 compatibility**: `asyncio.get_event_loop()` no longer auto-creates an event loop. The `we-mp-rss/main.py` has been patched to use `asyncio.new_event_loop()` + `asyncio.set_event_loop()` before `asyncio.run()`.
- **Playwright dependency**: we-mp-rss requires Playwright browsers installed in its conda env (`playwright install chromium`). Without this, WeChat login QR code generation will fail.
- **Conda env required for we-mp-rss**: `gui_manager.py` uses `D:\miniconda3\envs\we-mp-rss\python.exe` to start we-mp-rss. Do not use system Python (missing dependencies like python-docx).
- **we-mp-rss Cookie 自动续期**: `we-mp-rss/driver/auth.py` 中 `renew_auth()` 每 6 小时用存储的 cookie 访问微信平台刷新会话，需 `WE_RSS.AUTH=True` 环境变量。启动脚本已配置。
- **we-mp-rss 定时采集**: 数据库中已有 MessageTask（每天 9:00 采集所有公众号）。添加新公众号后自动纳入，无需额外配置。we-mp-rss 的增量获取靠数据库去重（url+id），每次拉最新页。
- **we-mp-rss 过滤规则**: `filter_rules` 表是 HTML 内容清洗（移除广告/页脚等 DOM），不是文章筛选。不支持按标题/关键词过滤文章。
- **we-mp-rss 浏览器弹窗**: `driver/wxarticle.py` 文章内容抓取已改为 `headless=True`（2026-06-27），不再弹出浏览器窗口。扫码登录（`driver/wx.py`）保持有头模式。
- **we-mp-rss B: 盘弹窗**: `driver/playwright_driver.py` 的 `use_native_edge_profile` 必须为 `False`，否则会触发 Windows 驱动器枚举弹窗。
- **we-mp-rss GBK 编码**: `main.py` 的 UTF-8 修复只用 `sys.stdout.reconfigure()`，不要用 `io.TextIOWrapper(sys.stdout.buffer)` 替换（会触发 B: 盘弹窗）。
- **we-mp-rss Token 状态**: `getStatus()` 使用 `expiry_timestamp` 动态判断过期，`remaining_seconds` 是静态快照不可靠。
- **多事件支持**: Vision Prompt 返回 `events` 数组，一篇文章可创建多个 Event。每个 Event 独立去重。
- **RapidOCR**: `OCR_PROVIDER=rapid` 使用本地 RapidOCR（`pip install rapidocr_onnxruntime`），免费、快速（<1秒/张）。

## Handoff Notes
When continuing work, assume the following are already true unless a later failure shows otherwise:

- `we-mp-rss` subscription and authorization were previously completed
- real articles from `北大团委`, `北京大学百周年纪念讲堂`, `北京大学人文社会科学研究院`, `北京大学人文学部` have been ingested
- all current events have already been synced to Feishu once
- Vision API (智谱 AI GLM-4.6V) is configured and working
- automatic sync service is running (hourly cron)
- 11 Feishu views are created with proper filters (excluding past/expired/recap/archived)
- daily/weekly reports are sent to user's Feishu via `FEISHU_REPORT_USER_ID`
- Alembic migrations are up to date (4 migrations applied)
- 162 tests passing, CI pipeline configured
- Web management UI available at `http://localhost:8000/` (editorial campus bulletin design)
- Tray application manages both services, with dual-status icon and independent autostart
- SQLite WAL mode enabled for better concurrent read/write performance
- New accounts can be added following `docs/adding-accounts.md`
- we-mp-rss Cookie 自动续期已启用（每 6 小时），定时采集已配置（每天 9:00，所有公众号）

If you need repository-specific guidance for the collector service itself, also read:

- [we-mp-rss/AGENTS.md](E:/cctry/GoActivity/we-mp-rss/AGENTS.md)
