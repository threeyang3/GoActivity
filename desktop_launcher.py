"""Packaged desktop entry point; services keep their dedicated environments."""
import json
import os
import sys


def main():
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        import ctypes
        # Avoid leaking PyInstaller's DLL search directory to Python/Node.
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    from desktop.paths import project_root
    os.chdir(project_root())
    if "--supervise" in sys.argv:
        from desktop.supervisor import supervise
        return supervise([sys.executable, "--managed"], project_root())
    if "--smoke-test" in sys.argv:
        from PySide6.QtWidgets import QApplication
        from desktop.app import StatusWindow
        from desktop.autostart import AutostartManager
        from desktop.service_controller import ServiceController, find_goactivity_python, find_rss_python, check_health
        qt = QApplication(sys.argv)
        window = StatusWindow(ServiceController(), AutostartManager())
        result = {
            "root": str(project_root()),
            "goactivity_python": find_goactivity_python(),
            "collector_python": find_rss_python(),
            "goactivity_health": check_health("127.0.0.1", 8000),
            "collector_health": check_health("127.0.0.1", 8001, "/api/docs"),
            "qt_window": window.windowTitle(),
        }
        qt.processEvents()
        from pathlib import Path
        Path("logs/packaged-smoke.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        window.close()
        return 0
    from desktop.app import main as desktop_main
    return desktop_main()


if __name__ == "__main__":
    sys.exit(main())
