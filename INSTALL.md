# GoActivity 安装指南

## 快速安装（推荐）

### 一键安装

1. 双击运行 `setup.bat`
2. 按照提示完成安装
3. 安装完成后，桌面会出现快捷方式

### 手动安装

如果一键安装失败，可以手动执行以下步骤：

#### 1. 创建虚拟环境

```bash
python -m venv venv
```

#### 2. 激活虚拟环境

```bash
# Windows
venv\Scripts\activate.bat

# Linux/Mac
source venv/bin/activate
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

#### 4. 创建快捷方式

```bash
# Windows
create_shortcut.bat
```

---

## 启动方式

### 方式 1：GUI 管理器启动（推荐）

桌面快捷方式：
- **GoActivity 管理器** - 双击启动系统托盘应用

功能特性：
- ✅ 系统托盘显示绿色/红色图标（运行中/已停止）
- ✅ 右键菜单管理服务（启动/停止/重启）
- ✅ 双击查看服务状态
- ✅ 打开管理页面和日志
- ✅ 任务栏显示应用图标
- ✅ 开机自动启动服务

使用方法：
1. 双击桌面"GoActivity 管理器"快捷方式
2. 服务会自动启动，托盘显示绿色图标
3. 右键点击托盘图标可以管理服务
4. 双击托盘图标可以查看服务状态

### 方式 2：命令行启动

```bash
# 激活虚拟环境
venv\Scripts\activate.bat

# 启动服务
python start_service.py --start

# 或指定端口
python start_service.py --start --port 8080

# 或指定监听地址
python start_service.py --start --host 0.0.0.0 --port 8000
```

### 方式 3：Windows 服务（开机自启）

#### 安装服务

1. 以管理员身份运行 `install_service.bat`
2. 服务会自动安装并配置开机自启

#### 管理服务

```bash
# 启动服务
net start GoActivity

# 停止服务
net stop GoActivity

# 查看服务状态
nssm status GoActivity

# 卸载服务（以管理员身份运行）
install_service.bat --uninstall
```

---

## 访问地址

服务启动后，可以通过以下地址访问：

- **管理页面**: http://127.0.0.1:8000/docs
- **健康检查**: http://127.0.0.1:8000/health
- **API 文档**: http://127.0.0.1:8000/redoc

---

## 日志文件

日志文件位于 `logs/` 目录：

- `service.log` - 服务运行日志
- `service_stdout.log` - 标准输出日志（Windows 服务模式）
- `service_stderr.log` - 错误输出日志（Windows 服务模式）

---

## 常见问题

### 1. 端口被占用

如果 8000 端口被占用，可以指定其他端口：

```bash
python start_service.py --start --port 8080
```

### 2. 服务无法启动

检查日志文件：
```bash
type logs\service.log
```

### 3. 权限问题

安装 Windows 服务需要管理员权限：
- 右键点击 `install_service.bat`
- 选择"以管理员身份运行"

### 4. Python 环境问题

确保使用项目自带的虚拟环境：
```bash
venv\Scripts\python.exe --version
```

---

## 卸载

### 卸载 Windows 服务

1. 以管理员身份运行 `install_service.bat --uninstall`
2. 或者手动执行：
   ```bash
   nssm stop GoActivity
   nssm remove GoActivity confirm
   ```

### 删除项目

直接删除项目文件夹即可。

---

## 配置说明

### 环境变量

配置文件：`.env`

主要配置项：
- `APP_HOST` - 监听地址（默认：127.0.0.1）
- `APP_PORT` - 监听端口（默认：8000）
- `DATABASE_URL` - 数据库连接（默认：sqlite:///storage/app.db）

### Windows 服务配置

使用 NSSM 管理服务，配置文件位于注册表：
```
HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\GoActivity
```

---

## 技术架构

```
┌─────────────────────────────────────────┐
│           Windows 服务 (NSSM)            │
├─────────────────────────────────────────┤
│         GoActivity (FastAPI)             │
├─────────────────────────────────────────┤
│    Uvicorn (ASGI Server)                 │
├─────────────────────────────────────────┤
│    Python 虚拟环境 (venv)                │
└─────────────────────────────────────────┘
```

---

## 文件说明

| 文件 | 说明 |
|------|------|
| `setup.bat` | 一键安装脚本 |
| `start_service.py` | 服务启动脚本 |
| `install_service.bat` | Windows 服务安装脚本 |
| `create_shortcut.bat` | 快捷方式创建脚本 |
| `build.spec` | PyInstaller 打包配置 |
| `requirements.txt` | Python 依赖列表 |
| `.env` | 环境变量配置 |
| `logs/` | 日志目录 |
| `storage/` | 数据存储目录 |
