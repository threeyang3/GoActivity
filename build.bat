@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "BUILD_PYTHON=%~dp0storage\desktop-build\.venv\Scripts\python.exe"
if not exist "%BUILD_PYTHON%" set "BUILD_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%BUILD_PYTHON%" (
    echo 请先按 docs\reproducibility.md 恢复项目环境。
    exit /b 1
)
"%BUILD_PYTHON%" -c "import PyInstaller, PySide6" >nul 2>&1
if errorlevel 1 (
    echo 请在构建环境安装 PyInstaller 6.20.0 和 requirements-desktop.txt。
    exit /b 1
)
"%BUILD_PYTHON%" -m PyInstaller build.spec --noconfirm
if errorlevel 1 exit /b 1
echo 打包完成：dist\GoActivity\GoActivity.exe
echo 请保留整个产物文件夹和项目虚拟环境，详见 docs\desktop-package.md。
