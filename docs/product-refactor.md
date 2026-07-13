# 产品化重构记录

## 当前架构

- **后端**: FastAPI + SQLAlchemy + SQLite
- **前端**: 单文件 index.html (3360 行) → 已拆分为模块化 ES Modules
- **桌面**: tkinter + pystray → 已迁移到 PySide6
- **配置**: .env + pydantic-settings → 增加 SettingsService + Settings API

## 已完成项目

### 阶段一：正确性、安全性和基础缺陷

- [x] 清理重复路由 (events.py: PUT /events/{event_id}, POST /events/batch)
- [x] 默认监听 127.0.0.1，增加 allow_lan_access 和 admin_token
- [x] 写接口增加鉴权依赖 (require_admin)
- [x] 修复 GET 执行修改操作 (/accounts/update/{mp_id} → POST)
- [x] 健康检查三级状态 (ok/degraded/error)
- [x] 托盘状态支持 green/yellow/red/gray
- [x] 单实例机制 (SingleInstance 类，基于 TCP 端口锁)
- [x] 路由唯一性测试
- [x] 编辑活动后飞书同步失败不丢失本地修改
- [x] 手动同步、定时同步、启动归档统一互斥，避免完整链路并发执行
- [x] 远程 WeRSS Webhook 增加独立令牌认证

### 阶段二：配置中心

- [x] OCR/Vision/文本 AI 配置字段已拆分，旧字段保持兼容
- [x] SettingsService 统一设置服务
- [x] Settings API (GET/PUT/POST /settings/*)
- [x] Provider 测试接口 (/settings/test/*)
- [x] 密钥字段掩码返回
- [x] 切换存储目录时同步迁移运行时密钥文件
- [x] 运行时重载已接入 SettingsService / Scheduler / AutoSync / BotConsumer
- [x] .env.example 更新

### 阶段三：Web 管理后台

- [x] 拆分为模块化结构 (css/ + js/)
- [x] 六个一级页面 (总览/活动/公众号/自动化/集成与模型/系统)
- [x] 移除 Google Fonts 外部依赖
- [x] 移除宣传式大标题和无意义英文标签
- [x] 统一设计 Token (tokens.css)
- [x] API 错误展示改进
- [x] 批量操作使用后端批量接口
- [x] 设置页面可调整 OCR/Vision/文本 AI
- [x] Provider 测试功能
- [x] 总览页按用户关注度重排：链路健康、今日/未来活动、待处理、最近同步
- [x] 系统页改为“运行概览 / 详细设置”双标签，降低首屏纵向长度
- [x] 公众号页兼容 we-mp-rss `data.list` 返回结构，恢复真实账号卡片展示
- [x] 主内容区取消不必要限宽，桌面与移动端自适应布局补齐
- [x] 前端路由支持 `#accounts` / `#system` 等深链接直达，便于直接验收子页面
- [x] 飞书 11 个主视图已在真实 Base 中逐个验证；对脏视图增加自动校验与重建兜底
- [x] 本地 RapidOCR 依赖已验证安装，健康检查恢复为 `ok`

### 阶段四：桌面程序

- [x] 迁移到 PySide6
- [x] 分离 ServiceController (可独立测试)
- [x] SingleInstance 单实例锁
- [x] 托盘菜单层级重新整理
- [x] 状态窗口支持高 DPI
- [x] 修复 start_service stdout PIPE 阻塞风险
- [x] Windows 服务安装默认绑定地址改为受配置约束
- [x] 移除硬编码路径 (D:\miniconda3)
- [x] 健康检查在后台执行
- [x] 自动重启复用原监控线程，避免监控线程随重启次数累积

### 阶段五：数据与时间字段

- [x] 新增 `events.start_at` / `end_at` / `timezone` / `raw_time_text`
- [x] 新增 `app_settings` 表
- [x] 关键查询优先兼容规范时间字段
- [x] Alembic 迁移已补充（旧库升级路径）

### 阶段五：测试

- [x] 路由唯一性测试
- [x] 健康检查测试
- [x] 设置 API 测试
- [x] 鉴权测试
- [x] 205 tests passing

### 阶段六：链路自动化与可观测性

- [x] 飞书失败同步持久化、指数退避与重试耗尽标记
- [x] 同步指标拆分为扫描、候选、处理、新建、跳过及飞书结果
- [x] 公众号级数据新鲜度、文章/活动产出与 SLA 状态
- [x] 优先公众号高频采集，并在采集后接续完整同步
- [x] 每日飞书 Base 分页对账与保守缺失记录修复
- [x] 连续失败、待办积压、低置信度、公众号过期及对账差异告警
- [x] 自动化管理页展示、手动采集与安全修复入口

## 兼容性决策

- 旧 VISION_API_* 字段仍可用于 Vision Provider (向后兼容)
- 新增 OCR_API_*, TEXT_AI_API_* 字段用于独立配置
- .env 文件格式不变，新增字段追加
- 数据库 Schema 已新增运行时设置表与规范时间字段

## 未完成项目

- 飞书 Bitable 视图数量动态获取
- 飞书 Keyring 密钥存储
- 完整的桌面程序图标资产
- 总览页空态与高密度数据场景的进一步视觉微调
- 飞书旧遗留视图（非当前 11 个主视图）仍可能保留，需要单独清理策略
- 纯 Alembic 空库 `upgrade head` 仍受早期初始迁移设计限制，需要后续单独整治
