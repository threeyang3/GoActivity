@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity 服务安装脚本
echo ========================================
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 请以管理员身份运行此脚本！
    echo 右键点击此文件，选择"以管理员身份运行"
    pause
    exit /b 1
)

:: 设置变量
set "SERVICE_NAME=GoActivity"
set "SERVICE_DISPLAY_NAME=GoActivity 校园活动知识库服务"
set "SERVICE_DESCRIPTION=GoActivity - 校园活动采集、处理和飞书同步服务"
set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH=%SCRIPT_DIR%venv\Scripts\python.exe"
set "SCRIPT_PATH=%SCRIPT_DIR%start_service.py"

:: 检查 Python 环境
if not exist "%PYTHON_PATH%" (
    echo [错误] 未找到 Python 虚拟环境
    echo 请先运行: python -m venv venv
    echo 然后运行: pip install -r requirements.txt
    pause
    exit /b 1
)

:: 检查 NSSM
where nssm >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 未找到 NSSM，正在下载...

    :: 创建临时目录
    mkdir "%TEMP%\nssm_download" 2>nul

    :: 下载 NSSM
    echo 正在下载 NSSM...
    powershell -Command "Invoke-WebRequest -Uri 'https://nssm.cc/release/nssm-2.24.zip' -OutFile '%TEMP%\nssm_download\nssm.zip'"

    if exist "%TEMP%\nssm_download\nssm.zip" (
        echo 正在解压 NSSM...
        powershell -Command "Expand-Archive -Path '%TEMP%\nssm_download\nssm.zip' -DestinationPath '%TEMP%\nssm_download' -Force"

        :: 复制到系统目录
        copy "%TEMP%\nssm_download\nssm-2.24\win64\nssm.exe" "C:\Windows\System32\" >nul
        if %errorlevel% equ 0 (
            echo NSSM 安装成功
        ) else (
            echo [错误] NSSM 安装失败，请手动下载 NSSM
            echo 下载地址: https://nssm.cc/download
            pause
            exit /b 1
        )
    ) else (
        echo [错误] NSSM 下载失败
        echo 请手动下载 NSSM: https://nssm.cc/download
        pause
        exit /b 1
    )
)

:: 创建日志目录
if not exist "%SCRIPT_DIR%logs" mkdir "%SCRIPT_DIR%logs"

echo.
echo 正在安装服务...
echo.

:: 停止已存在的服务
nssm stop %SERVICE_NAME% >nul 2>&1
nssm remove %SERVICE_NAME% confirm >nul 2>&1

:: 安装服务
nssm install %SERVICE_NAME% "%PYTHON_PATH%" "\"%SCRIPT_PATH%\" --start --host 0.0.0.0 --port 8000"
if %errorlevel% neq 0 (
    echo [错误] 服务安装失败
    pause
    exit /b 1
)

:: 配置服务
nssm set %SERVICE_NAME% DisplayName "%SERVICE_DISPLAY_NAME%"
nssm set %SERVICE_NAME% Description "%SERVICE_DESCRIPTION%"
nssm set %SERVICE_NAME% Start SERVICE_AUTO_START
nssm set %SERVICE_NAME% AppDirectory "%SCRIPT_DIR%"
nssm set %SERVICE_NAME% AppStdout "%SCRIPT_DIR%logs\service_stdout.log"
nssm set %SERVICE_NAME% AppStderr "%SCRIPT_DIR%logs\service_stderr.log"
nssm set %SERVICE_NAME% AppRotateFiles 1
nssm set %SERVICE_NAME% AppRotateBytes 10485760

:: 设置恢复选项（失败后自动重启）
nssm set %SERVICE_NAME% AppExit Default Restart
nssm set %SERVICE_NAME% AppRestartDelay 5000

echo.
echo ========================================
echo   服务安装成功！
echo ========================================
echo.
echo 服务名称: %SERVICE_NAME%
echo 显示名称: %SERVICE_DISPLAY_NAME%
echo 启动类型: 自动（开机自启）
echo.
echo 可用命令:
echo   启动服务: net start %SERVICE_NAME%
echo   停止服务: net stop %SERVICE_NAME%
echo   查看状态: nssm status %SERVICE_NAME%
echo.

:: 询问是否立即启动
set /p "START_NOW=是否立即启动服务？(Y/N): "
if /i "%START_NOW%"=="Y" (
    echo.
    echo 正在启动服务...
    nssm start %SERVICE_NAME%
    if %errorlevel% equ 0 (
        echo 服务启动成功！
        echo.
        echo 访问地址: http://127.0.0.1:8000
        echo API 文档: http://127.0.0.1:8000/docs
    ) else (
        echo [错误] 服务启动失败，请查看日志
    )
)

echo.
pause
