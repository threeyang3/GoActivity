@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity GUI 管理器启动
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"

:: 检查 Python 环境
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python
    pause
    exit /b 1
)

:: 检查依赖
python -c "import pystray; from PIL import Image" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在安装 GUI 依赖...
    pip install pystray pillow
    if %errorlevel% neq 0 (
        echo [错误] 安装依赖失败
        pause
        exit /b 1
    )
)

:: 启动 GUI 管理器
echo 正在启动 GUI 管理器...
echo 启动后会在系统托盘显示图标
echo.
start /b pythonw gui_manager.py

echo [✓] GUI 管理器已启动
echo.
echo 功能说明:
echo   - 系统托盘显示绿色图标表示服务运行中
echo   - 右键点击图标可以管理服务
echo   - 双击图标可以查看服务状态
echo.
echo 按任意键退出此窗口（服务将继续运行）...
pause >nul
