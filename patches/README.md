# 采集服务改进补丁

`we-mp-rss-runtime.patch` 保存本项目当前运行的采集端源码改进。采集服务是独立 Git 仓库，主项目忽略整个 `we-mp-rss/`，因此将其定制源码以补丁形式一起版本管理。

基准仓库：`https://github.com/rachelos/we-mp-rss.git`。

基准提交：`804b867a`（完整提交 ID 见补丁目录的 `collector-base.txt`）。补丁包含后端、二维码生成/登录修复、会话续期、无头文章抓取、前端扫码修复、构建依赖调整、按需加载及限频去重测试。未包含配置、数据库、Cookie、二维码图片、前端构建产物或本机 `node_modules` 删除。

在新机器上先获取固定版本，再应用补丁：

```powershell
git clone https://github.com/rachelos/we-mp-rss.git we-mp-rss
git -C we-mp-rss checkout (Get-Content patches/collector-base.txt).Trim()
git -C we-mp-rss switch -c codex/collector-runtime
.\.venv\Scripts\python.exe scripts/apply-collector-patch.py --check
.\.venv\Scripts\python.exe scripts/apply-collector-patch.py
```

完成采集服务依赖和 Playwright 浏览器安装后，重建前端：

```powershell
cd we-mp-rss/web_ui
npm ci
npm run build
Copy-Item -Path dist/* -Destination ../static -Recurse -Force
```

使用兼容 Vite 8 的 Node.js（本机已验证 Node.js 24）。新机器仍需自行填写配置和扫码登录；补丁不携带这些数据。以后升级上游时，在单独分支验证补丁和测试，出现冲突应先解决后再启动服务。

安装脚本 `scripts/bootstrap-project.py` 自动完成上述步骤，包括将构建结果部署到 `static/`。应用脚本会检查已应用状态，不会重复修改；已有其他本地定制时，需要先解决补丁冲突，脚本不会覆盖它们。
