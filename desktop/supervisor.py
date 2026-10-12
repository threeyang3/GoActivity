"""Small task-owned supervisor; normal GUI exits stay stopped."""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess
import sys
import time


def supervise(command, root: Path, run=subprocess.run, wait=time.sleep):
    logger = logging.getLogger("desktop.supervisor")
    (root / "logs").mkdir(exist_ok=True)
    handler = RotatingFileHandler(root / "logs/desktop-supervisor.log", maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    failures = 0
    try:
        while True:
            started = time.monotonic()
            try:
                result = run(command, cwd=str(root), check=False)
                code = result.returncode
            except OSError:
                code = 1
            if code == 0:
                return 0
            if time.monotonic() - started >= 300:
                failures = 0
            delay = min(300, 5 * 2 ** min(failures, 6))
            failures += 1
            logger.warning("Desktop exited with code %s; retry in %s seconds", code, delay)
            wait(delay)
    finally:
        logger.removeHandler(handler)
        handler.close()
