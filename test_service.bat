@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity 服务测试
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
echo [2/3] 检查依赖包...
python -c "import fastapi; import uvicorn; import sqlalchemy" >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 缺少依赖包，请运行: pip install -r requirements.txt
    pause
    exit /b 1
)
echo [✓] 依赖包完整

:: 测试启动服务
echo.
echo [3/3] 测试启动服务...
echo 正在启动服务（5秒后自动停止）...
echo.

:: 启动服务
start /b python start_service.py --start --port 8000

:: 等待服务启动
timeout /t 3 /nobreak >nul

:: 测试健康检查
echo 测试健康检查接口...
curl -s http://127.0.0.1:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [✓] 服务启动成功！
    echo.
    echo 服务地址: http://127.0.0.1:8000
    echo API 文档: http://127.0.0.1:8000/docs
) else (
    echo [!] 服务可能未完全启动，请稍等片刻后访问
)

:: 等待用户查看
timeout /t 5 /nobreak >nul

:: 停止服务
echo.
echo 正在停止服务...
taskkill /f /im python.exe >nul 2>&1

echo.
echo ========================================
echo   测试完成！
echo ========================================
echo.
echo 如果服务正常，你可以:
echo   1. 双击桌面"GoActivity 启动服务"快捷方式
echo   2. 或运行: python start_service.py --start
echo.
pause
