@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity 禁用开机自启
echo ========================================
echo.

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\GoActivity 管理器.lnk"

if exist "%SHORTCUT_PATH%" (
    del "%SHORTCUT_PATH%"
    echo [✓] 开机自启已禁用
    echo.
    echo 快捷方式已从启动文件夹删除:
    echo %SHORTCUT_PATH%
) else (
    echo [!] 开机自启未启用
    echo.
    echo 启动文件夹中没有找到 GoActivity 快捷方式
)

echo.
echo 如需重新启用，请运行: enable_autostart.bat
echo.
pause
