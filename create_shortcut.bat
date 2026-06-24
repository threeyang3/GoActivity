@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   GoActivity 快捷方式创建脚本
echo ========================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH=%SCRIPT_DIR%venv\Scripts\python.exe"
set "PYTHONW_PATH=%SCRIPT_DIR%venv\Scripts\pythonw.exe"
set "SCRIPT_PATH=%SCRIPT_DIR%start_service.py"
set "GUI_PATH=%SCRIPT_DIR%gui_manager.py"

:: 检查 Python 环境
if not exist "%PYTHON_PATH%" (
    echo [错误] 未找到 Python 虚拟环境
    echo 请先运行: python -m venv venv
    echo 然后运行: pip install -r requirements.txt
    pause
    exit /b 1
)

:: 创建 VBS 脚本来生成快捷方式
echo 正在创建快捷方式...

:: 创建桌面快捷方式 - GUI 管理器（推荐）
(
echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
echo sLinkFile = oWS.SpecialFolders^("Desktop"^) ^& "\GoActivity 管理器.lnk"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
echo oLink.TargetPath = "%PYTHONW_PATH%"
echo oLink.Arguments = """%GUI_PATH%"""
echo oLink.WorkingDirectory = "%SCRIPT_DIR%"
echo oLink.Description = "GoActivity 系统托盘管理器"
echo oLink.WindowStyle = 7
echo oLink.Save
) > "%TEMP%\create_gui_shortcut.vbs"

cscript //nologo "%TEMP%\create_gui_shortcut.vbs"
if %errorlevel% equ 0 (
    echo [✓] 桌面快捷方式创建成功: GoActivity 管理器.lnk
) else (
    echo [✗] 桌面快捷方式创建失败
)

:: 创建桌面快捷方式 - 命令行启动
(
echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
echo sLinkFile = oWS.SpecialFolders^("Desktop"^) ^& "\GoActivity 命令行启动.lnk"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
echo oLink.TargetPath = "%PYTHON_PATH%"
echo oLink.Arguments = """%SCRIPT_PATH%"" --start --host 0.0.0.0 --port 8000"
echo oLink.WorkingDirectory = "%SCRIPT_DIR%"
echo oLink.Description = "GoActivity 命令行启动"
echo oLink.WindowStyle = 1
echo oLink.Save
) > "%TEMP%\create_cmd_shortcut.vbs"

cscript //nologo "%TEMP%\create_cmd_shortcut.vbs"
if %errorlevel% equ 0 (
    echo [✓] 命令行快捷方式创建成功: GoActivity 命令行启动.lnk
) else (
    echo [✗] 命令行快捷方式创建失败
)

:: 创建桌面快捷方式 - 打开管理页面
(
echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
echo sLinkFile = oWS.SpecialFolders^("Desktop"^) ^& "\GoActivity 管理页面.url"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
echo oLink.TargetPath = "http://127.0.0.1:8000/docs"
echo oLink.Save
) > "%TEMP%\create_url_shortcut.vbs"

cscript //nologo "%TEMP%\create_url_shortcut.vbs"
if %errorlevel% equ 0 (
    echo [✓] 管理页面快捷方式创建成功: GoActivity 管理页面.url
) else (
    echo [✗] 管理页面快捷方式创建失败
)

:: 创建启动菜单快捷方式
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\GoActivity"
if not exist "%START_MENU%" mkdir "%START_MENU%"

:: GUI 管理器快捷方式
(
echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
echo sLinkFile = "%START_MENU%\GoActivity 管理器.lnk"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
echo oLink.TargetPath = "%PYTHONW_PATH%"
echo oLink.Arguments = """%GUI_PATH%"""
echo oLink.WorkingDirectory = "%SCRIPT_DIR%"
echo oLink.Description = "GoActivity 系统托盘管理器"
echo oLink.WindowStyle = 7
echo oLink.Save
) > "%TEMP%\create_startmenu_gui.vbs"

cscript //nologo "%TEMP%\create_startmenu_gui.vbs"
if %errorlevel% equ 0 (
    echo [✓] 开始菜单快捷方式创建成功
) else (
    echo [✗] 开始菜单快捷方式创建失败
)

:: 启动服务快捷方式
(
echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
echo sLinkFile = "%START_MENU%\启动服务.lnk"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
echo oLink.TargetPath = "%PYTHON_PATH%"
echo oLink.Arguments = """%SCRIPT_PATH%"" --start --host 0.0.0.0 --port 8000"
echo oLink.WorkingDirectory = "%SCRIPT_DIR%"
echo oLink.Description = "启动 GoActivity 服务"
echo oLink.WindowStyle = 1
echo oLink.Save
) > "%TEMP%\create_startmenu_start.vbs"

cscript //nologo "%TEMP%\create_startmenu_start.vbs"
if %errorlevel% equ 0 (
    echo [✓] 启动服务快捷方式创建成功
) else (
    echo [✗] 启动服务快捷方式创建失败
)

:: 卸载服务快捷方式
(
echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
echo sLinkFile = "%START_MENU%\卸载服务.lnk"
echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
echo oLink.TargetPath = "%SCRIPT_DIR%install_service.bat"
echo oLink.Arguments = "--uninstall"
echo oLink.WorkingDirectory = "%SCRIPT_DIR%"
echo oLink.Description = "卸载 GoActivity 服务"
echo oLink.WindowStyle = 1
echo oLink.Save
) > "%TEMP%\create_startmenu_uninstall.vbs"

cscript //nologo "%TEMP%\create_startmenu_uninstall.vbs"
if %errorlevel% equ 0 (
    echo [✓] 卸载快捷方式创建成功
) else (
    echo [✗] 卸载快捷方式创建失败
)

:: 清理临时文件
del "%TEMP%\create_*.vbs" 2>nul

echo.
echo ========================================
echo   快捷方式创建完成！
echo ========================================
echo.
echo 已创建以下快捷方式:
echo.
echo 桌面:
echo   - GoActivity 管理器.lnk (系统托盘管理，推荐)
echo   - GoActivity 命令行启动.lnk (命令行启动)
echo   - GoActivity 管理页面.url (打开 API 文档)
echo.
echo 开始菜单:
echo   - GoActivity 管理器.lnk
echo   - 启动服务.lnk
echo   - 卸载服务.lnk
echo.
echo 使用说明:
echo   1. 双击"GoActivity 管理器"启动系统托盘应用
echo   2. 服务会自动启动，托盘显示绿色图标
echo   3. 右键点击托盘图标可以管理服务
echo   4. 双击托盘图标可以查看服务状态
echo.
pause
