@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity 开机自启设置
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PYTHONW_PATH=%SCRIPT_DIR%venv\Scripts\pythonw.exe"
set "GUI_PATH=%SCRIPT_DIR%gui_manager.py"
set "ICON_PATH=%SCRIPT_DIR%app_icon_modern.ico"

:: 检查 Python 环境
if not exist "%PYTHONW_PATH%" (
    echo [错误] 未找到 Python 虚拟环境
    echo 请先运行: python -m venv venv
    pause
    exit /b 1
)

:: 获取启动文件夹路径
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "START_MENU_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\GoActivity"

echo 启动文件夹: %STARTUP_FOLDER%
echo.

:: 创建启动文件夹快捷方式
echo [1/2] 创建开机自启快捷方式...

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%STARTUP_FOLDER%\GoActivity 管理器.lnk'); $Shortcut.TargetPath = '%PYTHONW_PATH%'; $Shortcut.Arguments = '%GUI_PATH%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = 'GoActivity 系统托盘管理器'; $Shortcut.IconLocation = '%ICON_PATH%,0'; $Shortcut.WindowStyle = 7; $Shortcut.Save()"

if %errorlevel% equ 0 (
    echo [✓] 开机自启快捷方式创建成功
) else (
    echo [✗] 开机自启快捷方式创建失败
)

:: 创建开始菜单快捷方式（用于手动启动）
echo.
echo [2/2] 更新开始菜单快捷方式...

if not exist "%START_MENU_FOLDER%" mkdir "%START_MENU_FOLDER%"

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU_FOLDER%\GoActivity 管理器.lnk'); $Shortcut.TargetPath = '%PYTHONW_PATH%'; $Shortcut.Arguments = '%GUI_PATH%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = 'GoActivity 系统托盘管理器'; $Shortcut.IconLocation = '%ICON_PATH%,0'; $Shortcut.WindowStyle = 7; $Shortcut.Save()"

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU_FOLDER%\打开管理页面.url'); $Shortcut.TargetPath = 'http://127.0.0.1:8000/docs'; $Shortcut.Save()"

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%START_MENU_FOLDER%\禁用开机自启.lnk'); $Shortcut.TargetPath = '%SCRIPT_DIR%disable_autostart.bat'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Description = '禁用 GoActivity 开机自启'; $Shortcut.Save()"

echo [✓] 开始菜单快捷方式更新成功

echo.
echo ========================================
echo   设置完成！
echo ========================================
echo.
echo 开机自启已启用！
echo.
echo 说明:
echo   - 下次开机时，GoActivity 管理器会自动启动
echo   - 服务会自动在后台运行
echo   - 系统托盘会显示图标
echo.
echo 管理方式:
echo   - 开始菜单 → GoActivity → 禁用开机自启
echo   - 或删除启动文件夹中的快捷方式:
echo     %STARTUP_FOLDER%\GoActivity 管理器.lnk
echo.
echo 测试:
echo   1. 重启电脑验证是否自动启动
echo   2. 或运行: start_gui.bat
echo.
pause
