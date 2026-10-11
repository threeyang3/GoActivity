# 从 GitHub 复现完整功能

主仓库包含 GoActivity 服务、Web 管理界面、桌面托盘、数据库模型与 8 个迁移、OCR/Vision 抽取、飞书记录/附件同步、视图初始化、日报/周报、机器人和自动调度。

文章抓取由独立的 we-mp-rss 提供。主仓库包含固定上游提交 ID 和完整定制源码补丁，可恢复二维码登录、文章/图片抓取、会话续期、采集定时任务、前端登录改进和限频去重。它不是一个只包含 GoActivity、缺少采集端实现的项目；但需要联网获取固定上游源码，并应用补丁。

## 新 Windows 机器安装

已验证的目标环境：Windows x64，Python 3.11（GoActivity）、Python 3.13（采集端）、Node.js 24 和 Git。安装这些工具后：

```powershell
git clone https://github.com/threeyang3/GoActivity.git
cd GoActivity
py -3.11 scripts/bootstrap-project.py --go-python py --collector-python py
```

也可通过 `--go-python` 和 `--collector-python` 指定两个 Python 的完整路径。安装 uv 的机器可额外使用 `--uv <uv.exe路径>`；本机 uv 需要把 `UV_CACHE_DIR` 指向 `E:\Develop\.runtimes\uv-cache`。

脚本执行：固定版本获取采集端、校验并应用补丁、创建两个独立 `.venv`、安装固定依赖、安装 Playwright Chromium、通过 `npm ci` 构建前端并部署到采集端 `static/`、生成本地配置、初始化数据库。现有配置和数据库不会被替换。新采集库的管理员账号使用随机密码，保存在本地 `we-mp-rss/data/bootstrap-admin.json`，不会显示在终端或提交到 Git。

Python 依赖通过 `constraints-runtime.txt`、`constraints-collector.txt` 及采集端上游 requirements 固定；前端使用补丁中的 `package-lock.json`。`requirements-desktop.txt` 和 `requirements-ocr.txt` 分别提供托盘和本地 OCR。旧 `setup.bat` 仅准备部分主服务环境，不是完整双服务安装入口。

## 必须自行配置的部分

1. 启动 `.\.venv\Scripts\python.exe -m desktop.app`，打开采集后台并用本地初始化凭据登录；完成微信扫码授权。
2. 在采集后台添加公众号和采集任务；创建 API Access Key/Secret Key，填入主项目 `.env` 的 `WE_MP_RSS_ACCESS_KEY` / `WE_MP_RSS_SECRET_KEY`。当前本机的 9 个订阅和任务在采集数据库中，不会随 Git 自动复制。GoActivity 的优先采集调度可覆盖全部已订阅公众号；如要使用采集端每日任务，应在采集后台新建。
3. 启用真实识别：设 `OCR_PROVIDER=rapid`；设置真实 `VISION_API_PROVIDER`、密钥、地址和模型。`.env.example` 默认使用 mock，只用于本地验证，不能替代真实活动识别。本机验证的 Vision 配置为 `openai_compatible` + `https://open.bigmodel.cn/api/paas/v4` + `glm-4.6v`，密钥自行提供。
4. 安装并授权飞书 CLI：`npm install -g @larksuite/cli@1.0.97`，运行 `lark-cli config init` 和 `lark-cli auth login --domain base,drive,im`。Windows 可用 `%APPDATA%\npm\lark-cli.cmd`，把完整路径填入 `FEISHU_CLI_PATH`。设置 `FEISHU_PROVIDER=lark_cli`、Base/Table 标识和海报附件字段，配置目标用户/群与报告调度；准备真实写入后设 `FEISHU_DRY_RUN=false`。
5. 创建或确认飞书表格字段，参见 [表格设置](feishu-bitable-setup.md)。通过 `POST /setup/feishu-views` 创建视图。需要机器人时设置应用信息、权限/事件订阅并启用 `FEISHU_BOT_ENABLED`。相关凭据和机器人授权不会由 Git 自动恢复。
6. 托盘的开机自启需要在新机器上自行启用；注册表项和本机安装路径不随源码迁移。

检查 `/health`、`/accounts/authorization` 和 `/automation/status`。完成订阅与授权后触发采集，再通过 `POST /sync/auto` 和 `GET /sync/status` 验证从文章入库到飞书的全链路。

## 复现边界

可以复现软件代码和功能，不能仅通过 `git clone` 自动得到这台机器的运行状态。Git 不包含 `.env`、采集配置、微信 Cookie、飞书登录、Vision API 密钥、数据库、历史文章/图片、订阅列表以及个人开机启动配置。需要保留历史状态时，应另外迁移安全备份；两个 SQLite 数据库都需要一致性备份，主服务 `storage/articles/` 和 `storage/images/` 也需复制，不能只搬源码。

微信/飞书/模型 API 可用性、权限和限频是外部条件。当前微信返回 `200013` 时会按 30/60/120 分钟冷却；源码不能保证解除限制，也不能在新机器上免扫码授权。

## 本次审查验证

- 从已提交源码创建独立副本，没有复制生产配置、凭据或数据；固定上游补丁应用和重复检查通过。
- 新建两个 Python 环境并重新安装全部依赖、运行 npm ci/前端构建、安装 Chromium和初始化新数据库。
- 主服务 229 项测试、采集端 7 项测试通过；修复了 Linux Windows 模拟测试和两个依赖个人飞书配置的测试。
- 独立端口 18000/18001 的两个服务启动通过，采集端首页和引用的前端资源均可访问；新主数据库健康正常，文档导出模块按需导入成功。
- 前端锁定依赖已修复本次 npm 审计发现的问题，最终审计报告 0 项；构建仍有上游大体积 chunk、国际化 eval 和动态导入提示，这些不是本次构建失败。
- 真实外部抓取、飞书写入和 Vision 调用沿用此前本机验证；此次干净副本验证没有使用个人授权或发送消息，不能视为全新账号的外部端到端实测。
