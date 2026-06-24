@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity 打包脚本
echo ========================================
echo.
echo 此脚本将项目打包成可执行文件
echo.

set "SCRIPT_DIR=%~dp0"

:: 检查 Python 环境
echo [1/4] 检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python
    pause
    exit /b 1
)
echo [✓] Python 环境正常

:: 检查 PyInstaller
echo.
echo [2/4] 检查 PyInstaller...
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在安装 PyInstaller...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo [错误] 安装 PyInstaller 失败
        pause
        exit /b 1
    )
)
echo [✓] PyInstaller 已安装

:: 清理旧的构建文件
echo.
echo [3/4] 清理旧的构建文件...
if exist "%SCRIPT_DIR%dist" rmdir /s /q "%SCRIPT_DIR%dist"
if exist "%SCRIPT_DIR%build" rmdir /s /q "%SCRIPT_DIR%build"
echo [✓] 清理完成

:: 执行打包
echo.
echo [4/4] 开始打包...
echo 这可能需要几分钟时间...
echo.

pyinstaller build.spec --clean --noconfirm
if %errorlevel% neq 0 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo   打包完成！
echo ========================================
echo.
echo 可执行文件位置: dist\GoActivity\GoActivity.exe
echo.
echo 使用方法:
echo   1. 将 dist\GoActivity 文件夹复制到目标电脑
echo   2. 双击 GoActivity.exe 启动服务
echo   3. 或使用命令行: GoActivity.exe --start --port 8000
echo.
echo 注意:
echo   - 首次运行需要配置 .env 文件
echo   - 数据库文件会自动创建在 storage 目录
echo   - 日志文件会自动创建在 logs 目录
echo.
pause
