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

### 需要重启

- 服务端口
- 监听地址
- 数据库地址
- 存储目录

## 密钥安全

- 密钥不写入普通设置表，当前默认保存在 `storage/settings.secrets.json`
- API 返回密钥时使用掩码（如 `sk-****abcd`）
- 日志中不记录密钥

## 局域网访问

默认仅监听 127.0.0.1。启用局域网访问：

1. 在设置页面开启 `allow_lan_access`
2. 配置 `admin_token`
3. 重启服务

局域网访问时，所有写接口需要 Bearer token 认证。
