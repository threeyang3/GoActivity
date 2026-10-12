"""Windows login auto-start support for the desktop manager."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - the desktop application is Windows-only
    winreg = None  # type: ignore[assignment]


AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_REG_NAME = "GoActivity"
RECOVERY_TASK_NAME = "GoActivity Desktop Recovery"


def recovery_task_command() -> str:
    return subprocess.list2cmdline([
        "powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
        f"Start-ScheduledTask -TaskName '{RECOVERY_TASK_NAME}'",
    ])


def build_autostart_command() -> str:
    """Return the command registered for the current application."""
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([str(Path(sys.executable).resolve())])

    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe")
    if pythonw.exists():
        python = pythonw
    project_root = Path(__file__).resolve().parent.parent
    bootstrap = (
        "import runpy,sys;"
        f"sys.path.insert(0,{str(project_root)!r});"
        "runpy.run_module('desktop.app',run_name='__main__')"
    )
    return subprocess.list2cmdline([str(python), "-c", bootstrap])


class AutostartManager:
    """Manage the current user's Windows Run registry entry."""

    def __init__(self, command: str | None = None):
        self.command = command or build_autostart_command()

    def is_enabled(self) -> bool:
        if os.name != "nt" or winreg is None:
            return False
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                AUTOSTART_REG_KEY,
                0,
                winreg.KEY_READ,
            ) as key:
                value, _ = winreg.QueryValueEx(key, AUTOSTART_REG_NAME)
            return bool(value)
        except OSError:
            return False

    def set_enabled(self, enabled: bool) -> None:
        if os.name != "nt" or winreg is None:
            raise OSError("开机自启仅支持 Windows")

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            AUTOSTART_REG_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    AUTOSTART_REG_NAME,
                    0,
                    winreg.REG_SZ,
                    self.command,
                )
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_REG_NAME)
                except FileNotFoundError:
                    pass

        if getattr(sys, "frozen", False):
            from desktop.paths import project_root
            script = project_root() / "scripts/install-desktop-task.ps1"
            try:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                     "-File", str(script), "-Mode", "Enable" if enabled else "Disable",
                     "-Executable", str(Path(sys.executable).resolve())],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=True,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise OSError("桌面故障恢复任务配置失败，请检查 Windows 任务计划程序权限。") from exc
            if enabled:
                # Both login entry points must start the same task, otherwise a
                # registry-launched instance could escape task supervision.
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, AUTOSTART_REG_NAME, 0, winreg.REG_SZ, recovery_task_command())
