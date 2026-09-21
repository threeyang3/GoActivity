"""GoActivity Desktop Manager — PySide6 System Tray Application.

Manages GoActivity and WeRSS services with system tray icon,
status window, and service control.
"""

import os
import sys
import webbrowser
from pathlib import Path

# Set working directory
os.chdir(Path(__file__).parent.parent)

from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.service_controller import ServiceController, ServiceState, check_health
from desktop.single_instance import SingleInstance
from desktop.autostart import AutostartManager

# Constants
SERVICE_HOST = "127.0.0.1"
SERVICE_PORT = 8000
RSS_HOST = "127.0.0.1"
RSS_PORT = 8001
ASSET_ICON = Path(__file__).parent / "assets" / "goactivity-logo.svg"


def create_tray_icon(color1: str = "gray", color2: str = "gray") -> QIcon:
    """Create a tray icon with dual status indicators."""
    size = 64
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background
    painter.setBrush(QColor(26, 46, 35))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)

    # Inner
    painter.setBrush(QColor(26, 92, 58))
    painter.drawRoundedRect(8, 8, 48, 48, 10, 10)

    # GA text
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Segoe UI", 16, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(8, 8, 48, 48, Qt.AlignmentFlag.AlignCenter, "GA")

    # Status colors
    colors = {
        "green": QColor(26, 92, 58),
        "red": QColor(192, 57, 43),
        "yellow": QColor(212, 160, 23),
        "gray": QColor(122, 122, 110),
    }

    # GoActivity indicator (top-right)
    painter.setPen(QColor(255, 255, 255, 200))
    painter.setBrush(colors.get(color1, colors["gray"]))
    painter.drawEllipse(48, 10, 12, 12)

    # WeRSS indicator (below)
    painter.setBrush(colors.get(color2, colors["gray"]))
    painter.drawEllipse(48, 26, 12, 12)

    painter.end()

    pixmap = QPixmap.fromImage(img)
    return QIcon(pixmap)


class StatusWorker(QThread):
    """Background worker for health checks."""
    status_updated = Signal(str, str)  # service_name, status

    def __init__(self, controller: ServiceController):
        super().__init__()
        self.controller = controller
        self._running = True

    def run(self):
        while self._running:
            # Check GoActivity
            status = check_health(SERVICE_HOST, SERVICE_PORT, "/health")
            self.status_updated.emit("goactivity", status)
            # Check WeRSS
            status = check_health(RSS_HOST, RSS_PORT, "/api/docs")
            self.status_updated.emit("werss", status)
            # Sleep
            for _ in range(30):  # Check every 30 seconds
                if not self._running:
                    return
                self.msleep(1000)

    def stop(self):
        self._running = False


class StatusWindow(QMainWindow):
    """Control center window."""

    def __init__(self, controller: ServiceController, autostart: AutostartManager):
        super().__init__()
        self.controller = controller
        self.autostart = autostart
        self.autostart_changed_callback = None
        self.setWindowTitle("GoActivity 控制中心")
        self.setMinimumSize(500, 400)
        self.resize(600, 500)
        if ASSET_ICON.exists():
            self.setWindowIcon(QIcon(str(ASSET_ICON)))

        # Central widget with tabs
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Overview tab
        tabs.addTab(self._create_overview_tab(), "概览")
        # Services tab
        tabs.addTab(self._create_services_tab(), "服务")
        # Config tab
        tabs.addTab(self._create_config_tab(), "配置")
        tabs.addTab(self._create_logs_tab(), "日志")

    def _create_overview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Status group
        status_group = QGroupBox("服务状态")
        status_layout = QGridLayout()

        self.ga_status_label = QLabel("检查中...")
        self.ga_status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.rss_status_label = QLabel("检查中...")
        self.rss_status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        status_layout.addWidget(QLabel("GoActivity:"), 0, 0)
        status_layout.addWidget(self.ga_status_label, 0, 1)
        status_layout.addWidget(QLabel("WeRSS:"), 1, 0)
        status_layout.addWidget(self.rss_status_label, 1, 1)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Quick actions
        actions_group = QGroupBox("快捷操作")
        actions_layout = QHBoxLayout()

        btn_admin = QPushButton("打开管理后台")
        btn_admin.clicked.connect(lambda: webbrowser.open(f"http://{SERVICE_HOST}:{SERVICE_PORT}/"))
        actions_layout.addWidget(btn_admin)

        btn_docs = QPushButton("API 文档")
        btn_docs.clicked.connect(lambda: webbrowser.open(f"http://{SERVICE_HOST}:{SERVICE_PORT}/docs"))
        actions_layout.addWidget(btn_docs)

        btn_logs = QPushButton("查看日志")
        btn_logs.clicked.connect(lambda: os.startfile("logs"))
        actions_layout.addWidget(btn_logs)

        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        layout.addStretch()
        return widget

    def _create_services_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # GoActivity
        ga_group = QGroupBox("GoActivity 服务")
        ga_layout = QGridLayout()

        self.ga_pid_label = QLabel("—")
        self.ga_addr_label = QLabel(f"http://{SERVICE_HOST}:{SERVICE_PORT}")
        self.ga_health_label = QLabel("—")

        ga_layout.addWidget(QLabel("PID:"), 0, 0)
        ga_layout.addWidget(self.ga_pid_label, 0, 1)
        ga_layout.addWidget(QLabel("地址:"), 1, 0)
        ga_layout.addWidget(self.ga_addr_label, 1, 1)
        ga_layout.addWidget(QLabel("健康:"), 2, 0)
        ga_layout.addWidget(self.ga_health_label, 2, 1)

        ga_btns = QHBoxLayout()
        btn_start = QPushButton("启动")
        btn_start.clicked.connect(lambda: self._run_in_thread(self.controller.start_goactivity))
        btn_stop = QPushButton("停止")
        btn_stop.clicked.connect(lambda: self._run_in_thread(self.controller.stop_goactivity))
        btn_restart = QPushButton("重启")
        btn_restart.clicked.connect(lambda: self._run_in_thread(self.controller.restart_goactivity))
        ga_btns.addWidget(btn_start)
        ga_btns.addWidget(btn_stop)
        ga_btns.addWidget(btn_restart)
        ga_layout.addLayout(ga_btns, 3, 0, 1, 2)

        ga_group.setLayout(ga_layout)
        layout.addWidget(ga_group)

        # WeRSS
        rss_group = QGroupBox("WeRSS 服务")
        rss_layout = QGridLayout()

        self.rss_pid_label = QLabel("—")
        self.rss_addr_label = QLabel(f"http://{RSS_HOST}:{RSS_PORT}")
        self.rss_health_label = QLabel("—")

        rss_layout.addWidget(QLabel("PID:"), 0, 0)
        rss_layout.addWidget(self.rss_pid_label, 0, 1)
        rss_layout.addWidget(QLabel("地址:"), 1, 0)
        rss_layout.addWidget(self.rss_addr_label, 1, 1)
        rss_layout.addWidget(QLabel("健康:"), 2, 0)
        rss_layout.addWidget(self.rss_health_label, 2, 1)

        rss_btns = QHBoxLayout()
        btn_start = QPushButton("启动")
        btn_start.clicked.connect(lambda: self._run_in_thread(self.controller.start_werss))
        btn_stop = QPushButton("停止")
        btn_stop.clicked.connect(lambda: self._run_in_thread(self.controller.stop_werss))
        btn_restart = QPushButton("重启")
        btn_restart.clicked.connect(lambda: self._run_in_thread(self.controller.restart_werss))
        rss_btns.addWidget(btn_start)
        rss_btns.addWidget(btn_stop)
        rss_btns.addWidget(btn_restart)
        rss_layout.addLayout(rss_btns, 3, 0, 1, 2)

        rss_group.setLayout(rss_layout)
        layout.addWidget(rss_group)

        layout.addStretch()
        return widget

    def _create_config_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info_group = QGroupBox("系统信息")
        info_layout = QGridLayout()

        info_layout.addWidget(QLabel("Python:"), 0, 0)
        info_layout.addWidget(QLabel(sys.executable), 0, 1)
        info_layout.addWidget(QLabel("工作目录:"), 1, 0)
        info_layout.addWidget(QLabel(str(Path.cwd())), 1, 1)
        info_layout.addWidget(QLabel("GoActivity 端口:"), 2, 0)
        info_layout.addWidget(QLabel(str(SERVICE_PORT)), 2, 1)
        info_layout.addWidget(QLabel("WeRSS 端口:"), 3, 0)
        info_layout.addWidget(QLabel(str(RSS_PORT)), 3, 1)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        startup_group = QGroupBox("启动设置")
        startup_layout = QVBoxLayout()
        self.autostart_checkbox = QCheckBox("登录 Windows 后自动启动 GoActivity")
        self.autostart_checkbox.setToolTip("自动启动桌面管理器，并由管理器启动 GoActivity 和 WeRSS 服务")
        self.autostart_checkbox.setChecked(self.autostart.is_enabled())
        self.autostart_checkbox.toggled.connect(self._set_autostart)
        startup_layout.addWidget(self.autostart_checkbox)
        startup_note = QLabel("启用后，桌面管理器会在后台启动，并自动运行 GoActivity 与 WeRSS。")
        startup_note.setWordWrap(True)
        startup_note.setStyleSheet("color: #666;")
        startup_layout.addWidget(startup_note)
        startup_group.setLayout(startup_layout)
        layout.addWidget(startup_group)

        layout.addStretch()
        return widget

    def _set_autostart(self, enabled: bool):
        try:
            self.autostart.set_enabled(enabled)
        except OSError as exc:
            self.autostart_checkbox.blockSignals(True)
            self.autostart_checkbox.setChecked(self.autostart.is_enabled())
            self.autostart_checkbox.blockSignals(False)
            QMessageBox.critical(self, "开机自启设置失败", str(exc))
            return

        if self.autostart_changed_callback:
            self.autostart_changed_callback(enabled, source="window")

    def sync_autostart_state(self, enabled: bool):
        """Update the checkbox without writing the registry again."""
        self.autostart_checkbox.blockSignals(True)
        self.autostart_checkbox.setChecked(enabled)
        self.autostart_checkbox.blockSignals(False)

    def _create_logs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        logs_group = QGroupBox("日志与诊断")
        logs_layout = QVBoxLayout()
        btn_logs = QPushButton("打开日志目录")
        btn_logs.clicked.connect(lambda: os.startfile("logs"))
        logs_layout.addWidget(btn_logs)
        logs_group.setLayout(logs_layout)
        layout.addWidget(logs_group)
        layout.addStretch()
        return widget

    def _run_in_thread(self, fn):
        """Run a function in a background thread."""
        import threading
        threading.Thread(target=fn, daemon=True).start()

    def update_status(self, svc_name: str, status: str):
        """Update status display (must be called from main thread)."""
        label = self.ga_status_label if svc_name == "goactivity" else self.rss_status_label
        pid_label = self.ga_pid_label if svc_name == "goactivity" else self.rss_pid_label
        health_label = self.ga_health_label if svc_name == "goactivity" else self.rss_health_label

        svc = self.controller.goactivity if svc_name == "goactivity" else self.controller.werss

        status_map = {
            "ok": ("✓ 正常", "color: #1a5c3a"),
            "running": ("✓ 运行中", "color: #1a5c3a"),
            "degraded": ("⚠ 降级", "color: #d4a017"),
            "starting": ("⟳ 启动中", "color: #d4a017"),
            "stopped": ("✗ 已停止", "color: #c0392b"),
            "error": ("✗ 错误", "color: #c0392b"),
            "unreachable": ("✗ 不可达", "color: #c0392b"),
            "unknown": ("? 未知", "color: #7a7a6e"),
        }
        text, style = status_map.get(status, (status, ""))
        label.setText(text)
        label.setStyleSheet(style)

        pid = svc.process.pid if svc.process else "—"
        pid_label.setText(str(pid))
        health_label.setText(status)


class GoActivityTray:
    """Main application with system tray."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        if ASSET_ICON.exists():
            self.app.setWindowIcon(QIcon(str(ASSET_ICON)))

        self.controller = ServiceController()
        self.autostart = AutostartManager()
        self.status_window = StatusWindow(self.controller, self.autostart)
        self.status_window.autostart_changed_callback = self._on_autostart_changed

        # Health check worker
        self.health_worker = StatusWorker(self.controller)
        self.health_worker.status_updated.connect(self._on_health_update)

        # System tray
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(create_tray_icon("gray", "gray"))
        self.tray.setToolTip("GoActivity 校园活动知识库")
        self.tray.activated.connect(self._on_tray_activated)

        # Tray menu
        self._build_menu()

        # Status tracking
        self.ga_status = "unknown"
        self.rss_status = "unknown"

    def _build_menu(self):
        menu = QMenu()

        # Open control center
        action_open = QAction("打开控制中心", menu)
        action_open.triggered.connect(self._show_status_window)
        menu.addAction(action_open)
        menu.setDefaultAction(action_open)

        # Open admin
        action_admin = QAction("打开管理后台", menu)
        action_admin.triggered.connect(lambda: webbrowser.open(f"http://{SERVICE_HOST}:{SERVICE_PORT}/"))
        menu.addAction(action_admin)

        menu.addSeparator()

        # Quick actions
        action_sync = QAction("立即同步", menu)
        action_sync.triggered.connect(self._trigger_sync)
        menu.addAction(action_sync)

        menu.addSeparator()

        # GoActivity submenu
        ga_menu = menu.addMenu("GoActivity")
        action_start_ga = QAction("启动", ga_menu)
        action_start_ga.triggered.connect(lambda: self._run_in_thread(self.controller.start_goactivity))
        ga_menu.addAction(action_start_ga)
        action_stop_ga = QAction("停止", ga_menu)
        action_stop_ga.triggered.connect(lambda: self._run_in_thread(self.controller.stop_goactivity))
        ga_menu.addAction(action_stop_ga)
        action_restart_ga = QAction("重启", ga_menu)
        action_restart_ga.triggered.connect(lambda: self._run_in_thread(self.controller.restart_goactivity))
        ga_menu.addAction(action_restart_ga)

        # WeRSS submenu
        rss_menu = menu.addMenu("WeRSS")
        action_start_rss = QAction("启动", rss_menu)
        action_start_rss.triggered.connect(lambda: self._run_in_thread(self.controller.start_werss))
        rss_menu.addAction(action_start_rss)
        action_stop_rss = QAction("停止", rss_menu)
        action_stop_rss.triggered.connect(lambda: self._run_in_thread(self.controller.stop_werss))
        rss_menu.addAction(action_stop_rss)
        action_restart_rss = QAction("重启", rss_menu)
        action_restart_rss.triggered.connect(lambda: self._run_in_thread(self.controller.restart_werss))
        rss_menu.addAction(action_restart_rss)

        menu.addSeparator()

        # Windows login auto-start
        self.action_autostart = QAction("开机自动启动", menu)
        self.action_autostart.setCheckable(True)
        self.action_autostart.setChecked(self.autostart.is_enabled())
        self.action_autostart.toggled.connect(self._set_autostart_from_tray)
        menu.addAction(self.action_autostart)

        menu.addSeparator()

        # Logs
        action_logs = QAction("日志", menu)
        action_logs.triggered.connect(lambda: os.startfile("logs"))
        menu.addAction(action_logs)

        menu.addSeparator()

        # Quit
        action_quit = QAction("退出", menu)
        action_quit.triggered.connect(self._quit)
        menu.addAction(action_quit)

        self.tray.setContextMenu(menu)

    def _set_autostart_from_tray(self, enabled: bool):
        try:
            self.autostart.set_enabled(enabled)
        except OSError as exc:
            self.action_autostart.blockSignals(True)
            self.action_autostart.setChecked(self.autostart.is_enabled())
            self.action_autostart.blockSignals(False)
            QMessageBox.critical(None, "开机自启设置失败", str(exc))
            return
        self._on_autostart_changed(enabled, source="tray")
        state = "已启用" if enabled else "已关闭"
        self.tray.showMessage("GoActivity", f"开机自启{state}")

    def _on_autostart_changed(self, enabled: bool, *, source: str):
        if source != "tray":
            self.action_autostart.blockSignals(True)
            self.action_autostart.setChecked(enabled)
            self.action_autostart.blockSignals(False)
        if source != "window":
            self.status_window.sync_autostart_state(enabled)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_status_window()

    def _show_status_window(self):
        self.status_window.show()
        self.status_window.raise_()
        self.status_window.activateWindow()

    def _on_health_update(self, service: str, status: str):
        """Called from health worker thread — must marshal to main thread."""
        if service == "goactivity":
            self.ga_status = status
        else:
            self.rss_status = status
        self._update_icon()
        self.status_window.update_status(service, status)

    def _update_icon(self):
        color_map = {
            "ok": "green", "running": "green",
            "degraded": "yellow", "starting": "yellow",
            "error": "red", "stopped": "red", "unreachable": "red",
            "unknown": "gray",
        }
        ga_color = color_map.get(self.ga_status, "gray")
        rss_color = color_map.get(self.rss_status, "gray")
        self.tray.setIcon(create_tray_icon(ga_color, rss_color))

    def _trigger_sync(self):
        import urllib.request
        try:
            url = f"http://{SERVICE_HOST}:{SERVICE_PORT}/sync/auto"
            req = urllib.request.Request(url, method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                import json
                data = json.loads(resp.read())
                self.tray.showMessage("GoActivity", f"同步状态: {data.get('status', '未知')}")
        except Exception as e:
            self.tray.showMessage("GoActivity", f"同步失败: {e}", QSystemTrayIcon.MessageIcon.Warning)

    def _run_in_thread(self, fn):
        import threading
        threading.Thread(target=fn, daemon=True).start()

    def _quit(self):
        self.health_worker.stop()
        self.controller.shutdown()
        self.tray.hide()
        self.app.quit()

    def run(self):
        """Run the application."""
        self.tray.show()
        self.health_worker.start()

        # Auto-start services
        self._run_in_thread(self.controller.start_goactivity)
        self._run_in_thread(self.controller.start_werss)

        return self.app.exec()


def main():
    """Main entry point."""
    # Single instance check
    lock = SingleInstance()
    if not lock.try_acquire():
        QMessageBox.warning(None, "GoActivity", "GoActivity 管理器已在运行")
        sys.exit(0)

    try:
        tray = GoActivityTray()
        exit_code = tray.run()
    finally:
        lock.release()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
