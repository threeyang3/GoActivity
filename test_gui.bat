@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity GUI 管理器测试
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"

:: 检查 Python 环境
echo [1/3] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python
    pause
    exit /b 1
)
echo [✓] Python 环境正常

:: 检查依赖
echo.
echo [2/3] 检查 GUI 依赖...
python -c "import pystray; from PIL import Image" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在安装 GUI 依赖...
    pip install pystray pillow --quiet
    if %errorlevel% neq 0 (
        echo [错误] 安装依赖失败
        pause
        exit /b 1
    )
)
echo [✓] GUI 依赖已安装

:: 测试 GUI 管理器
echo.
echo [3/3] 测试 GUI 管理器...
echo 正在启动 GUI 管理器（5秒后自动关闭）...
echo.

:: 启动 GUI 管理器
start /b pythonw gui_manager.py

:: 等待启动
timeout /t 3 /nobreak >nul

:: 检查是否在运行
tasklist | findstr pythonw >nul 2>&1
if %errorlevel% equ 0 (
    echo [✓] GUI 管理器启动成功！
    echo.
    echo 功能说明:
    echo   - 系统托盘显示绿色图标
    echo   - 右键点击图标可以管理服务
    echo   - 双击图标可以查看服务状态
    echo.
    echo 现在可以:
    echo   1. 双击桌面"GoActivity 管理器"快捷方式
    echo   2. 或运行: start_gui.bat
) else (
    echo [!] GUI 管理器可能未完全启动
)

:: 等待用户查看
timeout /t 5 /nobreak >nul

:: 关闭 GUI 管理器
echo.
echo 正在关闭 GUI 管理器...
taskkill /f /im pythonw.exe >nul 2>&1

echo.
echo ========================================
echo   测试完成！
echo ========================================
echo.
echo 如果测试成功，你可以:
echo   1. 运行 create_shortcut.bat 创建快捷方式
echo   2. 双击桌面"GoActivity 管理器"启动
echo.
pause
