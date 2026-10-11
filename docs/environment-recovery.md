# 本机环境恢复记录（2026-10-11）

工作目录为 `E:\Develop\GoActivity`。旧的 `E:\cctry\GoActivity` 和 `D:\miniconda3` 不存在，Miniconda 安装程序的执行被系统策略阻止，因此恢复为两个独立项目虚拟环境。

| 组件 | 路径或版本 |
| --- | --- |
| GoActivity | `.venv\Scripts\python.exe`，Python 3.11.17 |
| we-mp-rss | `we-mp-rss\.venv\Scripts\python.exe`，Python 3.13.16 |
| Python 基础安装 | `E:\Develop\.runtimes\python`，虚拟环境依赖此目录 |
| uv | `%LOCALAPPDATA%\GoActivity\tools\bin\uv.exe` |
| uv 下载缓存 | `E:\Develop\.runtimes\uv-cache` |
| 飞书 CLI | `%APPDATA%\npm\lark-cli.cmd`，1.0.97 |

GoActivity 已安装核心、桌面和 RapidOCR 依赖；采集服务已按其固定版本的 requirements 安装依赖，并安装 Playwright Chromium。两个环境的依赖不能混用。

## 启动与维护

双击根目录的 `start_gui.bat`，或在项目目录执行：

```powershell
.\.venv\Scripts\python.exe -m desktop.app
```

桌面管理器优先寻找项目 `.venv`，同时管理 8000 和 8001 两个服务。后台运行时可从托盘查看状态、启停或重启。用户随后已启用 Windows 登录后自动启动桌面管理器，由其启动两个服务。采集端源码修复保存在 [版本化补丁](../patches/README.md)。

需要补装依赖时使用 uv，并显式设置缓存位置，避免本机目录重定向导致跨盘重命名失败：

```powershell
$env:UV_CACHE_DIR = 'E:\Develop\.runtimes\uv-cache'
$uv = "$env:LOCALAPPDATA\GoActivity\tools\bin\uv.exe"
& $uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt -r requirements-desktop.txt -r requirements-ocr.txt
& $uv pip install --python .\we-mp-rss\.venv\Scripts\python.exe -r .\we-mp-rss\requirements.txt
```

## 外部授权

本机飞书 CLI 已完成配置和授权，用户及机器人身份均通过服务器验证。以下命令用于将来需要重新配置时；使用现有应用，在终端输入凭证，不要写入日志或提交到 Git：

```powershell
& "$env:APPDATA\npm\lark-cli.cmd" config init
& "$env:APPDATA\npm\lark-cli.cmd" auth login --domain base,drive,im
& "$env:APPDATA\npm\lark-cli.cmd" auth status --verify
```

采集后台地址为 `http://127.0.0.1:8001`。9 个订阅仍然存在；恢复时保存的微信会话已过期，用户随后已重新扫码，当前授权有效至 2026-10-15 16:49:29。后台登录与微信扫码是两个独立步骤。

## 已验证与限制

- GoActivity `/health` 和采集服务 `/api/docs` 返回 HTTP 200。
- 数据库、存储、采集 API、CLI 和 OCR 的本地健康项正常；自动同步、优先采集、飞书对账及日报/周报调度器已注册。
- Chromium 无头启动、页面创建和关闭通过；RapidOCR 对合成文字图片实际识别成功。
- 飞书 CLI 用户及机器人身份服务器验证通过；目标表格只读查询返回 136 条记录，其中 93 条有海报附件。本次没有进行人工飞书写入或发送报告。
- 桌面控制器、开机自启、Provider、健康检查及图片处理的 19 项测试在临时数据库中通过。
- 后续优化验证：全量测试在独立数据库、mock Provider 和禁用外部发送的配置下为 229 通过；旧日期 Webhook 测试已改为当前日期。采集端 7 项测试通过，详见 [运行优化记录](runtime-optimization.md)。
- `/health` 的 HTTP 200 不代表飞书授权、微信授权或数据新鲜度正常。恢复初期健康状态为 degraded，原因包括历史同步过期；需要等待一次成功同步后再次检查。

数据库与配置备份保存在 `storage/backups/environment-recovery-20261011-162433/`。备份含敏感配置，仅限本机保管，不要提交或上传。业务数据中的历史关联缺失未在本次环境恢复中修复。
