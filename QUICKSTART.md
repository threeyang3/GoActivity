# GoActivity 快速开始指南

## 📦 安装方式

### 方式一：一键安装（推荐）

```bash
# 双击运行
setup.bat
```

安装完成后，桌面会出现快捷方式。

### 方式二：手动安装

```bash
# 1. 创建虚拟环境
python -m venv venv

# 2. 激活虚拟环境
venv\Scripts\activate.bat

# 3. 安装依赖
pip install -r requirements.txt

# 4. 创建快捷方式
create_shortcut.bat
```

### 方式三：打包成可执行文件

```bash
# 运行打包脚本
build.bat

# 打包完成后，可执行文件在 dist\GoActivity 目录
```

---

## 🚀 启动服务

### GUI 管理器启动（推荐）

桌面快捷方式：
- **GoActivity 管理器** - 双击启动系统托盘应用

功能特性：
- ✅ 系统托盘显示绿色/红色图标（运行中/已停止）
- ✅ 右键菜单管理服务（启动/停止/重启）
- ✅ 双击查看服务状态
- ✅ 打开管理页面和日志
- ✅ 任务栏显示应用图标

### 命令行启动

```bash
# 激活虚拟环境
venv\Scripts\activate.bat

# 启动服务
python start_service.py --start

# 指定端口
python start_service.py --start --port 8080

# 指定监听地址（允许外部访问）
python start_service.py --start --host 0.0.0.0 --port 8000
```

### 设置开机自启（推荐）

```bash
# 启用开机自启
enable_autostart.bat

# 禁用开机自启
disable_autostart.bat

# 检查自启状态
check_autostart.bat
```

设置后：
- ✅ 开机自动启动 GUI 管理器
- ✅ 服务自动在后台运行
- ✅ 系统托盘显示图标
- ✅ 可随时禁用

### Windows 服务（高级选项）

```bash
# 以管理员身份运行
install_service.bat
```

安装后，服务会：
- ✅ 开机自动启动
- ✅ 在后台运行
- ✅ 可在任务管理器中查看
- ✅ 失败自动重启

---

## 🛠️ 管理服务

### Windows 服务管理

```bash
# 启动服务
net start GoActivity

# 停止服务
net stop GoActivity

# 查看状态
nssm status GoActivity

# 卸载服务（管理员）
install_service.bat --uninstall
```

### 任务管理器

1. 按 `Ctrl + Shift + Esc` 打开任务管理器
2. 切换到"服务"选项卡
3. 找到 "GoActivity" 服务
4. 右键可以启动/停止/重启

### 服务状态检查

```bash
# 健康检查
curl http://127.0.0.1:8000/health

# 查看 API 文档
# 浏览器打开: http://127.0.0.1:8000/docs
```

---

## 📁 文件结构

```
GoActivity/
├── setup.bat              # 一键安装脚本
├── start_service.py       # 服务启动脚本
├── install_service.bat    # Windows 服务安装
├── create_shortcut.bat    # 快捷方式创建
├── build.bat              # 打包脚本
├── build.spec             # PyInstaller 配置
├── test_service.bat       # 服务测试
├── requirements.txt       # Python 依赖
├── .env                   # 环境配置
├── INSTALL.md             # 详细安装文档
├── QUICKSTART.md          # 快速开始指南
├── app/                   # 应用代码
├── logs/                  # 日志目录
├── storage/               # 数据存储
└── venv/                  # Python 虚拟环境
```

---

## 🔧 配置说明

### 环境变量 (.env)

```bash
# 应用配置
APP_HOST=127.0.0.1
APP_PORT=8000

# 数据库
DATABASE_URL=sqlite:///storage/app.db

# 飞书配置
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
```

### 端口修改

如果默认端口 8000 被占用：

```bash
# 方式1：命令行指定
python start_service.py --start --port 8080

# 方式2：修改 .env 文件
APP_PORT=8080
```

---

## 📊 日志查看

### 实时查看日志

```bash
# Windows
type logs\service.log

# 或使用 PowerShell
Get-Content logs\service.log -Wait
```

### 日志文件位置

- `logs/service.log` - 应用日志
- `logs/service_stdout.log` - 标准输出（服务模式）
- `logs/service_stderr.log` - 错误输出（服务模式）

---

## ❓ 常见问题

### Q: 端口被占用怎么办？

```bash
# 查找占用端口的进程
netstat -ano | findstr :8000

# 终止进程（替换 PID）
taskkill /PID <PID> /F

# 或使用其他端口
python start_service.py --start --port 8080
```

### Q: 服务无法启动？

1. 检查日志文件
2. 确认端口未被占用
3. 确认 Python 环境正确
4. 以管理员身份运行

### Q: 如何开机自启？

```bash
# 安装为 Windows 服务（需要管理员权限）
install_service.bat
```

### Q: 如何允许外部访问？

```bash
# 监听所有地址
python start_service.py --start --host 0.0.0.0 --port 8000
```

注意：需要在防火墙中允许 8000 端口。

---

## 🎯 快速命令参考

| 操作 | 命令 |
|------|------|
| 一键安装 | `setup.bat` |
| 启动服务 | `python start_service.py --start` |
| 停止服务 | `Ctrl + C` |
| 安装服务 | `install_service.bat`（管理员） |
| 卸载服务 | `install_service.bat --uninstall`（管理员） |
| 启动 Windows 服务 | `net start GoActivity` |
| 停止 Windows 服务 | `net stop GoActivity` |
| 打包成 exe | `build.bat` |
| 测试服务 | `test_service.bat` |
| 创建快捷方式 | `create_shortcut.bat` |

---

## 📚 更多文档

- [详细安装文档](INSTALL.md)
- [API 文档](http://127.0.0.1:8000/docs)（服务启动后访问）
- [项目说明](README.md)
