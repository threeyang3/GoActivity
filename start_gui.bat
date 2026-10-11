@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity GUI 管理器启动
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
set "PYTHON_EXE=%GOACTIVITY_PYTHON%"
if not defined PYTHON_EXE if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
if not defined PYTHON_EXE set "PYTHON_EXE=D:\miniconda3\envs\goactivity\python.exe"

:: 检查 Python 环境
"%PYTHON_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python
    pause
    exit /b 1
)

:: 检查依赖
"%PYTHON_EXE%" -c "import PySide6" >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] GoActivity 环境缺少 PySide6，请安装 requirements-desktop.txt
    pause
    exit /b 1
)

:: 启动 GUI 管理器
echo 正在启动 GUI 管理器...
echo 启动后会在系统托盘显示图标
echo.
set "PYTHONW_EXE=%PYTHON_EXE:python.exe=pythonw.exe%"
start "" /b "%PYTHONW_EXE%" -m desktop.app

echo [✓] GUI 管理器已启动
echo.
echo 功能说明:
echo   - 系统托盘显示绿色图标表示服务运行中
echo   - 右键点击图标可以管理服务
echo   - 双击图标可以查看服务状态
echo.
echo 按任意键退出此窗口（服务将继续运行）...
pause >nul
