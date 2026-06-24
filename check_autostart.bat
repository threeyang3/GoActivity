@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity 开机自启状态检查
echo ========================================
echo.

set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\GoActivity 管理器.lnk"

echo 检查启动文件夹...
echo 路径: %STARTUP_FOLDER%
echo.

if exist "%SHORTCUT_PATH%" (
    echo [✓] 开机自启: 已启用
    echo.
    echo 快捷方式位置: %SHORTCUT_PATH%
) else (
    echo [✗] 开机自启: 未启用
    echo.
    echo 如需启用，请运行: enable_autostart.bat
)

echo.
echo ========================================
echo   相关文件
echo ========================================
echo.

echo 桌面快捷方式:
if exist "%USERPROFILE%\Desktop\GoActivity 管理器.lnk" (
    echo   [✓] %USERPROFILE%\Desktop\GoActivity 管理器.lnk
) else (
    echo   [✗] 未找到
)

echo.
echo 开始菜单:
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\GoActivity"
if exist "%START_MENU%\GoActivity 管理器.lnk" (
    echo   [✓] %START_MENU%\GoActivity 管理器.lnk
) else (
    echo   [✗] 未找到
)

echo.
echo 系统托盘图标:
if exist "%~dp0app_icon.ico" (
    echo   [✓] %~dp0app_icon.ico
) else (
    echo   [✗] 未找到
)

if exist "%~dp0app_icon_modern.ico" (
    echo   [✓] %~dp0app_icon_modern.ico
) else (
    echo   [✗] 未找到
)

echo.
pause
