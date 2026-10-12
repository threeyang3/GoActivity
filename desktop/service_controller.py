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
from functools import wraps
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from desktop.paths import project_root

logger = logging.getLogger(__name__)

SERVICE_PORT = 8000
SERVICE_HOST = "127.0.0.1"
RSS_PORT = 8001
RSS_HOST = "127.0.0.1"
PROJECT_ROOT = project_root()
RSS_DIR = PROJECT_ROOT / "we-mp-rss"

MAX_AUTO_RESTARTS = 3
RESTART_BACKOFF_BASE = 5  # seconds
RESTART_BACKOFF_MAX = 300
STABLE_RESET_SECONDS = 300


def serialized(service_name):
    def decorate(function):
        @wraps(function)
        def call(self, *args, **kwargs):
            with getattr(self, service_name)._control_lock:
                return function(self, *args, **kwargs)
        return call
    return decorate


def _find_python(env_var: str, project_dir: Path, conda_env: str) -> str:
    """Resolve a service interpreter without inheriting an incompatible GUI Python."""
    configured = os.environ.get(env_var)
    if configured and Path(configured).is_file():
        return configured

    candidates = [
        *(project_dir / sub / "Scripts" / "python.exe" for sub in (".venv", "venv")),
        Path(rf"D:\miniconda3\envs\{conda_env}\python.exe"),
        Path.home() / "miniconda3" / "envs" / conda_env / "python.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    if getattr(sys, "frozen", False):
        raise FileNotFoundError(f"未找到服务 Python：{env_var}；请先恢复项目虚拟环境。")
    return sys.executable


def find_goactivity_python() -> str:
    """Find the supported Python interpreter for GoActivity."""
    return _find_python("GOACTIVITY_PYTHON", PROJECT_ROOT, "goactivity")


def find_rss_python() -> str:
    """Find the supported Python interpreter for we-mp-rss."""
    return _find_python("WEMP_RSS_PYTHON", RSS_DIR, "we-mp-rss")


def service_environment() -> dict[str, str]:
    """Bound native compute pools before importing numerical libraries."""
    env = os.environ.copy()
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env.setdefault(key, "1")
    env.setdefault("PYTHONUTF8", "1")
    return env


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
            body = resp.read()
            # Some services expose only a docs/readiness URL.  A successful HTTP
            # response is healthy even when its body is HTML or has no status key.
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return "ok"
            if isinstance(data, dict) and "status" in data:
                return str(data["status"])
            return "ok"
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
    _control_lock: object = field(default_factory=threading.RLock, repr=False)
    _monitor_stop: object = field(default_factory=threading.Event, repr=False)
    _monitor_thread: object = field(default=None, repr=False)


class ServiceController:
    """Manages GoActivity and WeRSS services."""

    def __init__(self):
        self.goactivity = ServiceState(
            name="GoActivity", host=SERVICE_HOST, port=SERVICE_PORT,
            health_path="/health/live", log_path="logs/goactivity_service.log",
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

    @serialized("goactivity")
    def start_goactivity(self, *, start_monitor: bool = True) -> bool:
        """Start GoActivity service."""
        svc = self.goactivity
        svc.user_stopped = False
        if svc.running:
            return True

        # Check if already running externally
        if check_port(svc.host, svc.port):
            svc.running = True
            svc.managed = False
            svc.status = "running"
            self._notify(svc)
            if start_monitor:
                self._start_monitor(svc)
            return True

        try:
            cmd = [find_goactivity_python(), '-m', 'uvicorn', 'app.main:app', '--host', svc.host, '--port', str(svc.port)]
            if svc._log_handle:
                svc._log_handle.close()
            svc._log_handle = self._open_rotating_log(svc.log_path)
            svc.process = subprocess.Popen(
                cmd, cwd=str(PROJECT_ROOT), stdout=svc._log_handle, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                env=service_environment(),
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
            else:
                svc.status = "starting"

            # Start monitor
            if start_monitor:
                self._start_monitor(svc)
            return True
        except Exception as e:
            logger.error("Failed to start %s: %s", svc.name, e)
            svc.status = "stopped"
            svc.managed = True
            if start_monitor:
                self._start_monitor(svc)
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

    @serialized("werss")
    def start_werss(self, *, start_monitor: bool = True) -> bool:
        """Start WeRSS service."""
        svc = self.werss
        svc.user_stopped = False
        if svc.running:
            return True

        if check_port(svc.host, svc.port):
            svc.running = True
            svc.managed = False
            svc.status = "running"
            self._notify(svc)
            if start_monitor:
                self._start_monitor(svc)
            return True

        child_env = service_environment()
        child_env.setdefault("WE_RSS.AUTH", "True")
        try:
            cmd = [find_rss_python(), 'main.py', '-job', 'True', '-init', 'True']
            if svc._log_handle:
                svc._log_handle.close()
            svc._log_handle = self._open_rotating_log(svc.log_path)
            svc.process = subprocess.Popen(
                cmd, cwd=str(RSS_DIR), stdout=svc._log_handle, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                env=child_env,
            )
            svc.running = True
            svc.managed = True
            svc.user_stopped = False
            svc.status = "starting"
            self._notify(svc)

            ok = self._wait_health(svc, max_retries=20)
            if ok:
                svc.status = "running"
            else:
                svc.status = "starting"

            if start_monitor:
                self._start_monitor(svc)
            return True
        except Exception as e:
            logger.error("Failed to start %s: %s", svc.name, e)
            svc.status = "stopped"
            svc.managed = True
            if start_monitor:
                self._start_monitor(svc)
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
        svc.user_stopped = True
        svc._monitor_stop.set()
        with svc._control_lock:
            self._stop_service_locked(svc)

    def _stop_service_locked(self, svc: ServiceState):
        """Stop a service."""
        svc.user_stopped = True
        svc.restart_count = 0
        try:
            if svc.process:
                if sys.platform == 'win32':
                    # Windows venv launchers and the bot spawn child processes.
                    subprocess.run(
                        ['taskkill', '/PID', str(svc.process.pid), '/T', '/F'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=10,
                    )
                else:
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
            if health in {"ok", "degraded"}:
                return True
            if svc.user_stopped:
                return False
            time.sleep(interval)
        return False

    def _monitor_service(self, svc: ServiceState):
        """Monitor a service and auto-restart on failure."""
        consecutive_failures = 0
        stop_event = svc._monitor_stop
        stable_since = None
        while not stop_event.is_set():
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
                if self._restart_with_backoff(svc, stop_event):
                    svc.running = True
                    consecutive_failures = 0
                    stable_since = None
                    continue
                else:
                    if stop_event.is_set():
                        break
                    continue

            # Health check
            health = check_health(svc.host, svc.port, svc.health_path)
            if health == "ok":
                consecutive_failures = 0
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= STABLE_RESET_SECONDS:
                    svc.restart_count = 0
                if svc.status != "running":
                    svc.status = "running"
                    self._notify(svc)
            elif health == "degraded":
                consecutive_failures = 0
                if svc.status != "degraded":
                    svc.status = "degraded"
                    self._notify(svc)
            else:
                stable_since = None
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    svc.status = "unreachable"
                    self._notify(svc)
                    if not svc.user_stopped and (svc.managed or not check_port(svc.host, svc.port)):
                        # Try restart
                        if svc.process:
                            try:
                                self._terminate_process(svc.process)
                            except Exception:
                                pass
                            svc.process = None
                        svc.running = False
                        if self._restart_with_backoff(svc, stop_event):
                            svc.running = True
                            consecutive_failures = 0
                            continue
                        else:
                            if stop_event.is_set():
                                break
                else:
                    svc.status = "degraded"
                    self._notify(svc)

            stop_event.wait(10)

    def _start_monitor(self, svc):
        if svc._monitor_thread and svc._monitor_thread.is_alive() and not svc._monitor_stop.is_set():
            return
        svc._monitor_stop = threading.Event()
        svc._monitor_thread = threading.Thread(target=self._monitor_service, args=(svc,), daemon=True)
        svc._monitor_thread.start()

    @staticmethod
    def _terminate_process(process):
        if sys.platform == 'win32':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        else:
            process.terminate()
        process.wait(timeout=5)

    def _restart_with_backoff(self, svc: ServiceState, stop_event=None) -> bool:
        """Restart with exponential backoff."""
        stop_event = stop_event or svc._monitor_stop
        delay = min(RESTART_BACKOFF_MAX, RESTART_BACKOFF_BASE * (2 ** min(svc.restart_count, 6)))
        svc.restart_count += 1
        if stop_event.wait(delay) or svc.user_stopped:
            return False

        with svc._control_lock:
            if stop_event.is_set() or svc.user_stopped:
                return False
            if svc.name == "GoActivity":
                self.start_goactivity(start_monitor=False)
            else:
                self.start_werss(start_monitor=False)

        if svc.status == "running":
            return True
        return False

    def shutdown(self):
        """Stop all managed services."""
        self._stop_service(self.goactivity)
        self._stop_service(self.werss)
