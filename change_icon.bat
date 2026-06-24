@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity 图标更换工具
echo ========================================
echo.
echo 可用图标风格:
echo.
echo   1. 圆形风格 (app_icon.ico)
echo   2. 现代方形风格 (app_icon_modern.ico)
echo.
echo 当前使用: 现代方形风格
echo.

set /p "CHOICE=请选择图标风格 (1 或 2): "

if "%CHOICE%"=="1" (
    set "ICON_FILE=app_icon.ico"
    set "ICON_NAME=圆形风格"
) else if "%CHOICE%"=="2" (
    set "ICON_FILE=app_icon_modern.ico"
    set "ICON_NAME=现代方形风格"
) else (
    echo [错误] 无效的选择
    pause
    exit /b 1
)

echo.
echo 正在更换图标为 %ICON_NAME%...

set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH=%SCRIPT_DIR%venv\Scripts\python.exe"
set "GUI_PATH=%SCRIPT_DIR%gui_manager.py"
set "ICON_PATH=%SCRIPT_DIR%%ICON_FILE%"

:: 更新桌面快捷方式
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\GoActivity 管理器.lnk'); $Shortcut.IconLocation = '%ICON_PATH%,0'; $Shortcut.Save()"

:: 更新开始菜单快捷方式
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\GoActivity\GoActivity 管理器.lnk'); $Shortcut.IconLocation = '%ICON_PATH%,0'; $Shortcut.Save()"

echo.
echo ========================================
echo   图标更换完成！
echo ========================================
echo.
echo 已更换为: %ICON_NAME%
echo.
echo 提示: 如果图标没有立即更新，请:
echo   1. 刷新桌面 (F5)
echo   2. 或重启资源管理器
echo.
pause
