# Windows 桌面程序打包

当前打包入口是 `desktop_launcher.py`，生成 PySide6 双服务管理器。
程序使用项目的 `.venv` 与 `we-mp-rss/.venv` 启动服务，包含线程限制、进程树停止等运行优化。
它不包含服务环境、浏览器、凭证或数据库；不能只复制 exe 到另一台电脑直接运行。
新机器请先按 `docs/reproducibility.md` 恢复项目。

在项目根目录安装 PyInstaller 6.20.0 与 `requirements-desktop.txt` 后运行
`python -m PyInstaller build.spec --noconfirm`，或使用 `build.bat`。
推荐在独立构建环境中安装打包依赖，避免改变服务环境。

产物是整个 `dist/GoActivity/` 文件夹，入口为 `GoActivity.exe`。
请保留同目录的 `_internal` 文件夹。程序默认向上查找项目根目录，
也可通过 `GOACTIVITY_PROJECT_ROOT` 指定目录。

验证命令：`dist/GoActivity/GoActivity.exe --smoke-test`。
结果写入项目 `logs/packaged-smoke.json`，只包含目录、解释器、窗口名称与服务健康状态。
重复启动会直接退出，以保持单实例运行。

2026-10-12 起，开机自启通过当前用户的 `GoActivity Desktop Recovery` 计划任务执行；
桌面异常退出会由任务启动的守护进程重启，正常手动退出不会触发重启。配置脚本为
`scripts/install-desktop-task.ps1`，开机自启复选框同时管理该任务与登录入口。
数据库快照和故障恢复边界见 `docs/unattended-operation.md`。
