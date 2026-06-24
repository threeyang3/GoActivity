# we-mp-rss 服务管理脚本

## 快速开始

### 启动服务

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-we-mp-rss.ps1
```

### 停止服务

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-we-mp-rss.ps1
```

### 查看状态

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\status-we-mp-rss.ps1
```

## 开机自启动

### 安装任务计划（推荐）

```powershell
# 以管理员身份运行
powershell -ExecutionPolicy Bypass -File .\scripts\install-we-mp-rss-task.ps1
```

这会将 we-mp-rss 添加到 Windows 任务计划程序，开机时自动启动。

### 卸载任务计划

```powershell
# 以管理员身份运行
Unregister-ScheduledTask -TaskName "we-mp-rss" -Confirm:$false
```

## 手动管理

### 手动启动

```powershell
cd E:\cctry\GoActivity\we-mp-rss
conda activate we-mp-rss
python main.py -job True -init True
```

### 后台启动

```powershell
cd E:\cctry\GoActivity\we-mp-rss
Start-Process -FilePath "python" -ArgumentList "main.py -job True -init True" -WindowStyle Hidden
```

### 查看进程

```powershell
Get-Process | Where-Object {$_.ProcessName -like "*python*"}
```

### 停止进程

```powershell
Get-Process | Where-Object {$_.ProcessName -like "*python*"} | Stop-Process -Force
```

## 日志文件

- 标准输出：`E:\cctry\GoActivity\we-mp-rss\data\we-mp-rss-stdout.log`
- 错误日志：`E:\cctry\GoActivity\we-mp-rss\data\we-mp-rss-stderr.log`

## 配置文件

- 主配置：`E:\cctry\GoActivity\we-mp-rss\config.yaml`
- 环境变量：`E:\cctry\GoActivity\we-mp-rss\.env`

## 常见问题

### 1. 服务无法启动

检查日志文件，常见原因：
- 端口 8001 被占用
- Python 环境未激活
- 配置文件错误

### 2. 无法抓取文章

- 检查微信登录状态
- 检查网络连接
- 查看日志文件中的错误信息

### 3. 内存占用过高

- 调整抓取频率：修改 `config.yaml` 中的 `interval` 参数
- 减少同时抓取的文章数量：修改 `max_page` 参数

## 资源占用

| 资源 | 占用 |
|---|---|
| 内存 | ~35 MB |
| CPU | 几乎为 0 |
| 磁盘 | ~5 MB (SQLite) |
| 网络 | 只在抓取时访问 |

## 相关文档

- [we-mp-rss 官方文档](https://github.com/rachelos/we-mp-rss)
- [GoActivity 项目文档](../README.md)
