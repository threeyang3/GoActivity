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

# OCR Provider（独立配置）
OCR_API_KEY=
OCR_API_BASE_URL=https://api.openai.com/v1
OCR_API_MODEL=gpt-4o-mini

# 文本 AI Provider（独立配置）
TEXT_AI_PROVIDER=disabled
TEXT_AI_API_KEY=
TEXT_AI_API_BASE_URL=https://api.openai.com/v1
TEXT_AI_API_MODEL=gpt-4.1-mini
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

旧数据库升级请执行 `alembic upgrade head`。
注意：当前“纯空库直接 Alembic upgrade”仍受早期初始 migration 设计限制；应用自身首次启动仍可通过 `init_db()` 正常初始化并标记版本。

## 破坏性变更

- `/accounts/update/{mp_id}` 从 GET 改为 POST
- 管理页面完全重写，旧的自定义样式可能丢失
- `gui_manager.py` 不再是推荐的桌面程序入口
