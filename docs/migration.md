# 迁移指南

## 从旧版本升级

### 1. 更新代码

```bash
git pull
```

### 2. 更新依赖

```bash
pip install -r requirements.txt
```

### 3. 更新 .env

新增配置项（可选，有默认值）：

```env
# 服务安全
ALLOW_LAN_ACCESS=false
ADMIN_TOKEN=
WE_MP_RSS_WEBHOOK_TOKEN=

# OCR Provider（独立配置）
OCR_API_KEY=
OCR_API_BASE_URL=https://api.openai.com/v1
OCR_API_MODEL=gpt-4o-mini

# 文本 AI Provider（独立配置）
TEXT_AI_PROVIDER=disabled
TEXT_AI_API_KEY=
TEXT_AI_API_BASE_URL=https://api.openai.com/v1
TEXT_AI_API_MODEL=gpt-4.1-mini

# 自动化守护
AUTO_SYNC_STALE_MINUTES=180
FEISHU_SYNC_RETRY_MAX=6
FEISHU_SYNC_RETRY_BASE_MINUTES=15
PRIORITY_ACCOUNTS=
PRIORITY_COLLECTION_CRON=*/30 * * * *
ACCOUNT_STALE_HOURS=36
FEISHU_RECONCILE_ENABLED=true
FEISHU_RECONCILE_CRON=30 3 * * *
FEISHU_RECONCILE_MAX_MISSING_RATIO=0.2
FEISHU_RECONCILE_SNAPSHOT_HOURS=24
AUTOMATION_ALERTS_ENABLED=true
AUTOMATION_ALERT_COOLDOWN_HOURS=6
```

旧的 `VISION_API_*` 字段仍可用于 Vision Provider，无需修改。

### 4. 桌面程序（可选）

如需使用新的 PySide6 桌面程序：

```bash
pip install -r requirements-desktop.txt
python -m desktop.app
```

旧的 `gui_manager.py` 仍然可用。

### 5. 启动服务

```bash
# 方式 1：直接启动
python start_service.py

# 方式 2：桌面程序
python -m desktop.app

# 方式 3：uvicorn
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 回滚

如需回滚到旧版本：

```bash
git checkout <old-commit>
pip install -r requirements.txt
```

数据库 Schema 现已新增：

- `events.start_at`
- `events.end_at`
- `events.timezone`
- `events.raw_time_text`
- `app_settings`
- `events.feishu_retry_count`
- `events.feishu_next_retry_at`
- `events.feishu_last_error`
- `articles.ingestion_status`
- `articles.ingestion_reason`

当前迁移链共 8 个版本；本轮新增的 `f6a7b8c9d0e1_add_article_ingestion_state.py` 会为文章增加摄取状态和策略原因索引。升级后可用以下命令确认版本：

```powershell
D:\miniconda3\envs\goactivity\python.exe -m alembic current
```

文章摄取状态用于区分已处理、策略过滤和处理失败。过滤文章会保留轻量记录，后续自动同步会跳过已知结果，不会反复下载和抽取同一篇文章。

旧数据库升级请执行 `alembic upgrade head`。
注意：当前“纯空库直接 Alembic upgrade”仍受早期初始 migration 设计限制；应用自身首次启动仍可通过 `init_db()` 正常初始化并标记版本。

## 破坏性变更

- `/accounts/update/{mp_id}` 从 GET 改为 POST
- 管理页面完全重写，旧的自定义样式可能丢失
- `gui_manager.py` 不再是推荐的桌面程序入口
