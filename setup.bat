@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity 一键安装脚本
echo ========================================
echo.
echo 此脚本将完成以下操作:
echo   1. 创建 Python 虚拟环境
echo   2. 安装依赖包
echo   3. 创建快捷方式
echo   4. 安装 Windows 服务（可选）
echo.
echo 按任意键开始安装...
pause >nul

:: 设置变量
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%venv"
set "PYTHON_EXE=python"

:: 检查 Python
echo.
echo [1/4] 检查 Python 环境...
%PYTHON_EXE% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('%PYTHON_EXE% --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo [✓] Python 版本: %PYTHON_VERSION%

:: 创建虚拟环境
echo.
echo [2/4] 创建虚拟环境...
if exist "%VENV_DIR%" (
    echo [!] 虚拟环境已存在，跳过创建
) else (
    %PYTHON_EXE% -m venv "%VENV_DIR%"
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo [✓] 虚拟环境创建成功
)

:: 激活虚拟环境并安装依赖
echo.
echo [3/4] 安装依赖包...
call "%VENV_DIR%\Scripts\activate.bat"

:: 升级 pip
python -m pip install --upgrade pip >nul 2>&1

:: 安装依赖
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 安装依赖失败
    pause
    exit /b 1
)
echo [✓] 依赖包安装成功

:: 创建快捷方式
echo.
echo [4/4] 创建快捷方式...
call "%SCRIPT_DIR%create_shortcut.bat"

:: 询问是否安装服务
echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 是否要安装为 Windows 服务（开机自启）？
echo.
echo 注意: 安装服务需要管理员权限
echo.
set /p "INSTALL_SERVICE=是否安装服务？(Y/N): "
if /i "%INSTALL_SERVICE%"=="Y" (
    echo.
    echo 正在请求管理员权限...
    powershell -Command "Start-Process '%SCRIPT_DIR%install_service.bat' -Verb RunAs"
)

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 可用操作:
echo.
echo 1. 双击桌面"GoActivity 启动服务"快捷方式启动服务
echo 2. 或运行: venv\Scripts\python.exe start_service.py --start
echo 3. 访问 http://127.0.0.1:8000/docs 查看 API 文档
echo.
echo 如需卸载服务，请以管理员身份运行 install_service.bat --uninstall
echo.
pause
