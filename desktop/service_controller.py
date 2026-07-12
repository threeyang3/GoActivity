"""Service Controller — GoActivity & WeRSS service management.

Separated from GUI for testability.
"""

import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

SERVICE_PORT = 8000
SERVICE_HOST = "127.0.0.1"
RSS_PORT = 8001
RSS_HOST = "127.0.0.1"
RSS_DIR = Path(__file__).parent.parent / "we-mp-rss"

MAX_AUTO_RESTARTS = 3
RESTART_BACKOFF_BASE = 5  # seconds


def find_rss_python() -> str:
    """Find the Python interpreter for we-mp-rss."""
    # Check local venv first
    for sub in (".venv", "venv"):
        p = RSS_DIR / sub / "Scripts" / "python.exe"
        if p.exists():
            return str(p)
    return sys.executable


def check_port(host: str, port: int) -> bool:
    """Check if a port is in use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def check_health(host: str, port: int, path: str = "/health", timeout: int = 3) -> str:
    """Check service health. Returns 'ok', 'degraded', 'error', or 'unreachable'."""
    import urllib.request
    try:
        url = f"http://{host}:{port}{path}"
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("status", "error")
    except Exception:
        return "unreachable"


@dataclass
class ServiceState:
    """State of a managed service."""
    name: str
    host: str
    port: int
    health_path: str = "/health"
    process: subprocess.Popen | None = None
    running: bool = False
    status: str = "unknown"  # unknown, starting, running, degraded, stopped, unreachable
    restart_count: int = 0
    user_stopped: bool = False
    managed: bool = False  # True if started by this controller
    log_path: str = ""
    _log_handle: object = field(default=None, repr=False)


class ServiceController:
    """Manages GoActivity and WeRSS services."""

    def __init__(self):
        self.goactivity = ServiceState(
            name="GoActivity", host=SERVICE_HOST, port=SERVICE_PORT,
            health_path="/health", log_path="logs/goactivity_service.log",
        )
        self.werss = ServiceState(
            name="WeRSS", host=RSS_HOST, port=RSS_PORT,
            health_path="/api/docs", log_path="logs/werss_service.log",
        )
        self._monitor_threads: list[threading.Thread] = []
        self._on_status_change: Callable | None = None
        os.makedirs("logs", exist_ok=True)

    def set_status_callback(self, callback: Callable):
        """Set callback for status changes: callback(service_state)"""
        self._on_status_change = callback

    def _notify(self, svc: ServiceState):
        if self._on_status_change:
            try:
                self._on_status_change(svc)
            except Exception:
                pass

    @staticmethod
    def _open_rotating_log(path: str, max_bytes: int = 5 * 1024 * 1024):
        try:
            if os.path.exists(path) and os.path.getsize(path) > max_bytes:
                old = path + '.old'
                if os.path.exists(old):
                    os.remove(old)
                os.rename(path, old)
        except OSError:
            pass
        return open(path, 'a', encoding='utf-8')

    def start_goactivity(self) -> bool:
        """Start GoActivity service."""
        svc = self.goactivity
        if svc.running:
            return True

        # Check if already running externally
        if check_port(svc.host, svc.port):
            svc.running = True
            svc.managed = False
            svc.status = "running"
            self._notify(svc)
            return True

        cmd = [sys.executable, 'start_service.py', '--start', '--host', svc.host, '--port', str(svc.port)]
        try:
            svc._log_handle = self._open_rotating_log(svc.log_path)
            svc.process = subprocess.Popen(
                cmd, stdout=svc._log_handle, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )
            svc.running = True
            svc.managed = True
            svc.user_stopped = False
            svc.status = "starting"
            self._notify(svc)

            # Wait for health
            ok = self._wait_health(svc)
            if ok:
                svc.status = "running"
                svc.restart_count = 0
            else:
                svc.status = "starting"

            # Start monitor
            t = threading.Thread(target=self._monitor_service, args=(svc,), daemon=True)
            t.start()
            self._monitor_threads.append(t)
            return True
        except Exception as e:
            logger.error("Failed to start %s: %s", svc.name, e)
            svc.status = "stopped"
            self._notify(svc)
            return False

    def stop_goactivity(self):
        """Stop GoActivity service."""
        self._stop_service(self.goactivity)

    def restart_goactivity(self):
        """Restart GoActivity service."""
        self._stop_service(self.goactivity)
        time.sleep(1)
        self.start_goactivity()

    def start_werss(self) -> bool:
        """Start WeRSS service."""
        svc = self.werss
        if svc.running:
            return True

        if check_port(svc.host, svc.port):
            svc.running = True
            svc.managed = False
            svc.status = "running"
            self._notify(svc)
            return True

        rss_python = find_rss_python()
        cmd = [rss_python, 'main.py', '-job', 'True', '-init', 'True']
        try:
            svc._log_handle = self._open_rotating_log(svc.log_path)
            svc.process = subprocess.Popen(
                cmd, cwd=str(RSS_DIR), stdout=svc._log_handle, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )
            svc.running = True
            svc.managed = True
            svc.user_stopped = False
            svc.status = "starting"
            self._notify(svc)

            ok = self._wait_health(svc, max_retries=20)
            if ok:
                svc.status = "running"
                svc.restart_count = 0
            else:
                svc.status = "starting"

            t = threading.Thread(target=self._monitor_service, args=(svc,), daemon=True)
            t.start()
            self._monitor_threads.append(t)
            return True
        except Exception as e:
            logger.error("Failed to start %s: %s", svc.name, e)
            svc.status = "stopped"
            self._notify(svc)
            return False

    def stop_werss(self):
        """Stop WeRSS service."""
        self._stop_service(self.werss)

    def restart_werss(self):
        """Restart WeRSS service."""
        self._stop_service(self.werss)
        time.sleep(1)
        self.start_werss()

    def _stop_service(self, svc: ServiceState):
        """Stop a service."""
        svc.user_stopped = True
        svc.restart_count = 0
        if not svc.running:
            return
        try:
            if svc.process:
                svc.process.terminate()
                svc.process.wait(timeout=5)
        except Exception:
            if svc.process:
                svc.process.kill()
        svc.running = False
        svc.managed = False
        svc.process = None
        svc.status = "stopped"
        if svc._log_handle:
            try:
                svc._log_handle.close()
            except Exception:
                pass
            svc._log_handle = None
        self._notify(svc)

    def _wait_health(self, svc: ServiceState, max_retries: int = 15, interval: float = 2.0) -> bool:
        """Wait for service to become healthy."""
        for i in range(max_retries):
            health = check_health(svc.host, svc.port, svc.health_path)
            if health == "ok":
                return True
            if svc.user_stopped:
                return False
            time.sleep(interval)
        return False

    def _monitor_service(self, svc: ServiceState):
        """Monitor a service and auto-restart on failure."""
        consecutive_failures = 0
        while svc.running or svc.managed:
            if svc.user_stopped:
                break

            # Check process exit
            if svc.process and svc.process.poll() is not None:
                exit_code = svc.process.returncode
                svc.running = False
                svc.process = None
                svc.status = "stopped"
                self._notify(svc)
                if svc.user_stopped:
                    break
                # Auto-restart
                if self._restart_with_backoff(svc):
                    svc.running = True
                    consecutive_failures = 0
                    continue
                else:
                    break

            # Health check
            health = check_health(svc.host, svc.port, svc.health_path)
            if health == "ok":
                consecutive_failures = 0
                if svc.status != "running":
                    svc.status = "running"
                    self._notify(svc)
            elif health == "degraded":
                consecutive_failures = 0
                if svc.status != "degraded":
                    svc.status = "degraded"
                    self._notify(svc)
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    svc.status = "unreachable"
                    self._notify(svc)
                    if consecutive_failures == 3 and not svc.user_stopped:
                        # Try restart
                        if svc.process:
                            try:
                                svc.process.kill()
                            except Exception:
                                pass
                            svc.process = None
                        svc.running = False
                        if self._restart_with_backoff(svc):
                            svc.running = True
                            consecutive_failures = 0
                            continue
                        else:
                            break
                else:
                    svc.status = "degraded"
                    self._notify(svc)

            time.sleep(10)

    def _restart_with_backoff(self, svc: ServiceState) -> bool:
        """Restart with exponential backoff."""
        if svc.restart_count >= MAX_AUTO_RESTARTS:
            return False
        delay = RESTART_BACKOFF_BASE * (2 ** svc.restart_count)
        svc.restart_count += 1
        time.sleep(delay)
        if svc.user_stopped:
            return False

        if svc.name == "GoActivity":
            self.start_goactivity()
        else:
            self.start_werss()

        if svc.status == "running":
            svc.restart_count = 0
            return True
        return False

    def shutdown(self):
        """Stop all managed services."""
        self._stop_service(self.goactivity)
        self._stop_service(self.werss)
