"""Locate the external service workspace for source and packaged managers."""
import os
import sys
from pathlib import Path


def project_root() -> Path:
    configured = os.environ.get("GOACTIVITY_PROJECT_ROOT")
    if configured:
        candidates = [Path(configured).resolve()]
    elif getattr(sys, "frozen", False):
        location = Path(sys.executable).resolve().parent
        candidates = [location, *location.parents]
    else:
        return Path(__file__).resolve().parent.parent
    for candidate in candidates:
        if (candidate / "app/main.py").is_file() and (candidate / "we-mp-rss/main.py").is_file():
            return candidate
    raise FileNotFoundError("未找到 GoActivity 项目目录；请将程序放在项目内，或设置 GOACTIVITY_PROJECT_ROOT。")
