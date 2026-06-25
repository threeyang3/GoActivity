"""
GoActivity GUI 管理器
系统托盘应用，支持任务栏显示和托盘图标
"""

import os
import sys
import subprocess
import threading
import time
import json
import winreg
from pathlib import Path

# 设置工作目录
os.chdir(Path(__file__).parent)

# 检查依赖
try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    import tkinter as tk
    from tkinter import messagebox
except ImportError as e:
    print(f"缺少依赖: {e}")
    print("请运行: pip install pystray pillow")
    sys.exit(1)

# 常量
SERVICE_PORT = 8000
SERVICE_HOST = "127.0.0.1"
RSS_PORT = 8001
RSS_HOST = "127.0.0.1"
RSS_DIR = Path(__file__).parent / "we-mp-rss"
AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_REG_NAME = "GoActivity"
AUTOSTART_REG_NAME_RSS = "WeMpRss"


def _find_rss_python():
    """查找 we-mp-rss 的 Python 解释器"""
    for sub in (".venv", "venv"):
        p = RSS_DIR / sub / "Scripts" / "python.exe"
        if p.exists():
            return str(p)
    return sys.executable  # fallback: 共用当前环境


def _lighten(hex_color, factor=0.2):
    """将十六进制颜色变亮（factor 0~1）"""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f'#{r:02x}{g:02x}{b:02x}'


class GoActivityTray:
    """GoActivity 系统托盘管理器"""

    def __init__(self):
        self.process = None
        self.running = False
        self.service_status = "unknown"
        self.rss_process = None
        self.rss_running = False
        self.rss_service_status = "unknown"
        self.rss_python = _find_rss_python()
        self.icon = None
        self._status_window = None  # 状态窗口（独立 Toplevel）

        # 创建日志目录
        os.makedirs('logs', exist_ok=True)

        # 创建图标
        self.icon_image = self.create_icon()

        # 创建隐藏的 tkinter 根窗口（必须在主线程）
        self.root = tk.Tk()
        self.root.withdraw()  # 隐藏根窗口

    def create_icon(self, color='gray', rss_color='gray'):
        """创建托盘图标 — 深绿底 + 双状态指示灯"""
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 状态颜色映射
        status_colors = {
            'green': (26, 92, 58),    # #1a5c3a  运行中
            'red':   (192, 57, 43),   # #c0392b  已停止
            'gray':  (122, 122, 110), # #7a7a6e  未知
        }
        dot_color = status_colors.get(color, status_colors['gray'])
        rss_dot_color = status_colors.get(rss_color, status_colors['gray'])

        # 深森林绿圆角矩形背景
        draw.rounded_rectangle(
            [(2, 2), (62, 62)],
            radius=14,
            fill=(26, 46, 35)  # #1a2e23
        )

        # 内部绿色圆角矩形
        draw.rounded_rectangle(
            [(8, 8), (56, 56)],
            radius=10,
            fill=(26, 92, 58)  # #1a5c3a
        )

        # GA 文字
        try:
            font = ImageFont.truetype("segoeui.ttf", 20)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except (OSError, IOError):
                font = ImageFont.load_default()
        draw.text((32, 24), "GA", fill=(255, 255, 255), font=font, anchor="mt")

        # 底部小字
        try:
            small = ImageFont.truetype("segoeui.ttf", 6)
        except (OSError, IOError):
            small = font
        draw.text((32, 44), "Activity", fill=(255, 255, 255, 160), font=small, anchor="mt")

        # 右侧双指示灯（上 = GoActivity，下 = WeRSS）
        dot_r = 5
        # GoActivity 指示灯
        draw.ellipse(
            [54 - dot_r, 14 - dot_r, 54 + dot_r, 14 + dot_r],
            fill=dot_color, outline=(255, 255, 255, 200), width=1
        )
        # WeRSS 指示灯
        draw.ellipse(
            [54 - dot_r, 28 - dot_r, 54 + dot_r, 28 + dot_r],
            fill=rss_dot_color, outline=(255, 255, 255, 200), width=1
        )

        # 右下角状态指示灯
        dot_x, dot_y, dot_r = 54, 54, 7
        draw.ellipse(
            [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
            fill=dot_color,
            outline=(255, 255, 255, 200),
            width=2
        )

        return img

    def check_service_health(self):
        """检查服务健康状态"""
        import urllib.request
        try:
            url = f"http://{SERVICE_HOST}:{SERVICE_PORT}/health"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                return data.get("status", "error")
        except Exception:
            return "unreachable"

    def start_service(self):
        """启动服务"""
        if self.running:
            return

        # 检查端口是否被占用
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((SERVICE_HOST, SERVICE_PORT))
        sock.close()
        if result == 0:
            # 端口已被占用，服务可能已在运行
            self.running = True
            self.update_icon('green')
            self.service_status = "running"
            return

        # 创建启动脚本
        cmd = [
            sys.executable,
            'start_service.py',
            '--start',
            '--host', '0.0.0.0',
            '--port', str(SERVICE_PORT)
        ]

        try:
            # 启动服务进程
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            self.running = True

            # 等待服务启动
            time.sleep(2)

            # 检查服务是否启动成功
            health = self.check_service_health()
            if health == "ok":
                self.update_icon('green')
                self.service_status = "running"
                self.show_notification("GoActivity", "服务已启动")
            else:
                self.update_icon('yellow')
                self.service_status = "starting"

            # 启动监控线程
            threading.Thread(target=self.monitor_service, daemon=True).start()

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"启动服务失败: {e}"))

    def stop_service(self):
        """停止服务"""
        if not self.running:
            return

        try:
            if self.process:
                self.process.terminate()
                self.process.wait(timeout=5)
        except Exception:
            if self.process:
                self.process.kill()

        self.running = False
        self.process = None
        self.update_icon('red')
        self.service_status = "stopped"
        self.show_notification("GoActivity", "服务已停止")

    def restart_service(self):
        """重启服务"""
        self.stop_service()
        time.sleep(1)
        self.start_service()

    # ── WeRSS 服务管理 ──────────────────────────────────────────────

    def _check_rss_port(self):
        """检查 we-mp-rss 端口是否被占用"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((RSS_HOST, RSS_PORT))
        sock.close()
        return result == 0

    def check_rss_health(self):
        """检查 we-mp-rss 健康状态"""
        import urllib.request
        try:
            url = f"http://{RSS_HOST}:{RSS_PORT}/api/docs"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=3) as resp:
                return "ok" if resp.status == 200 else "error"
        except Exception:
            return "unreachable"

    def start_rss_service(self):
        """启动 we-mp-rss 服务"""
        if self.rss_running:
            return

        if self._check_rss_port():
            self.rss_running = True
            self.update_icon('green')
            self.rss_service_status = "running"
            return

        cmd = [self.rss_python, 'main.py', '-job', 'True', '-init', 'True']

        try:
            self.rss_process = subprocess.Popen(
                cmd,
                cwd=str(RSS_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )
            self.rss_running = True

            time.sleep(3)

            health = self.check_rss_health()
            if health == "ok":
                self.update_icon(rss_color='green')
                self.rss_service_status = "running"
                self.show_notification("WeRSS", "服务已启动")
            else:
                self.update_icon(rss_color='yellow')
                self.rss_service_status = "starting"

            threading.Thread(target=self.monitor_rss_service, daemon=True).start()

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"启动 WeRSS 失败: {e}"))

    def stop_rss_service(self):
        """停止 we-mp-rss 服务"""
        if not self.rss_running:
            return

        try:
            if self.rss_process:
                self.rss_process.terminate()
                self.rss_process.wait(timeout=5)
        except Exception:
            if self.rss_process:
                self.rss_process.kill()

        self.rss_running = False
        self.rss_process = None
        self.update_icon(rss_color='red')
        self.rss_service_status = "stopped"
        self.show_notification("WeRSS", "服务已停止")

    def restart_rss_service(self):
        """重启 we-mp-rss 服务"""
        self.stop_rss_service()
        time.sleep(1)
        self.start_rss_service()

    def monitor_rss_service(self):
        """监控 we-mp-rss 服务状态"""
        while self.rss_running:
            if self.rss_process and self.rss_process.poll() is not None:
                self.rss_running = False
                self.update_icon(rss_color='red')
                self.rss_service_status = "stopped"
                self.show_notification("WeRSS", "服务意外停止")
                break

            health = self.check_rss_health()
            if health == "ok":
                self.update_icon(rss_color='green')
                self.rss_service_status = "running"
            else:
                self.update_icon(rss_color='red')
                self.rss_service_status = "unreachable"

            time.sleep(10)

    def monitor_service(self):
        """监控服务状态"""
        while self.running:
            if self.process and self.process.poll() is not None:
                # 服务意外停止
                self.running = False
                self.update_icon('red')
                self.service_status = "stopped"
                self.show_notification("GoActivity", "服务意外停止")
                break

            # 定期检查健康状态
            health = self.check_service_health()
            if health == "ok":
                self.update_icon('green')
                self.service_status = "running"
            elif health == "degraded":
                self.update_icon('yellow')
                self.service_status = "degraded"
            else:
                self.update_icon('red')
                self.service_status = "unreachable"

            time.sleep(10)

    def update_icon(self, color=None, rss_color=None):
        """更新托盘图标（双指示灯）"""
        if self.icon:
            ga_color = color if color is not None else self.service_status
            rss_c = rss_color if rss_color is not None else self.rss_service_status
            # 映射 status 字符串或颜色名到图标颜色
            color_map = {
                "running": "green", "stopped": "red",
                "starting": "yellow", "degraded": "yellow",
                "unreachable": "red", "unknown": "gray",
                "green": "green", "red": "red",
                "yellow": "yellow", "gray": "gray",
            }
            self.icon_image = self.create_icon(
                color=color_map.get(ga_color, 'gray'),
                rss_color=color_map.get(rss_c, 'gray'),
            )
            self.icon.icon = self.icon_image

    def show_notification(self, title, message):
        """显示通知"""
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def open_browser(self):
        """打开浏览器"""
        import webbrowser
        webbrowser.open(f'http://{SERVICE_HOST}:{SERVICE_PORT}/')

    def open_api_docs(self):
        """打开 API 文档"""
        import webbrowser
        webbrowser.open(f'http://{SERVICE_HOST}:{SERVICE_PORT}/docs')

    def open_logs(self):
        """打开日志目录"""
        os.startfile('logs')

    def open_rss_browser(self):
        """打开 WeRSS 管理后台"""
        import webbrowser
        webbrowser.open(f'http://{RSS_HOST}:{RSS_PORT}/')

    def trigger_sync(self):
        """触发同步"""
        import urllib.request
        try:
            url = f"http://{SERVICE_HOST}:{SERVICE_PORT}/sync/auto"
            req = urllib.request.Request(url, method='POST')
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                msg = f"同步完成！\n拉取文章: {data.get('articles_fetched', 0)}\n同步事件: {data.get('events_synced', 0)}\n失败: {data.get('events_failed', 0)}"
                self.show_notification("GoActivity", msg)
        except Exception as e:
            self.show_notification("GoActivity", f"同步失败: {e}")

    def send_daily_report(self):
        """发送日报"""
        import urllib.request
        try:
            url = f"http://{SERVICE_HOST}:{SERVICE_PORT}/reports/daily?send_to_feishu=true"
            req = urllib.request.Request(url, method='POST')
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                if data.get('feishu_sent'):
                    self.show_notification("GoActivity", "日报已发送到飞书！")
                else:
                    self.show_notification("GoActivity", f"日报发送失败: {data.get('feishu_error', '未知错误')}")
        except Exception as e:
            self.show_notification("GoActivity", f"发送失败: {e}")

    def send_weekly_report(self):
        """发送周报"""
        import urllib.request
        try:
            url = f"http://{SERVICE_HOST}:{SERVICE_PORT}/reports/weekly?send_to_feishu=true"
            req = urllib.request.Request(url, method='POST')
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                if data.get('feishu_sent'):
                    self.show_notification("GoActivity", "周报已发送到飞书！")
                else:
                    self.show_notification("GoActivity", f"周报发送失败: {data.get('feishu_error', '未知错误')}")
        except Exception as e:
            self.show_notification("GoActivity", f"发送失败: {e}")

    def show_status(self):
        """显示服务状态窗口（线程安全，通过 root.after 调度到主线程）"""
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, self.show_status)
            return

        if self._status_window is not None and self._status_window.winfo_exists():
            self._status_window.deiconify()
            self._status_window.lift()
            self._status_window.focus_force()
            return

        # ── 设计常量 ──
        BG       = "#faf8f0"
        DARK     = "#1a2e23"
        CARD_BG  = "#ffffff"
        ACCENT   = "#1a5c3a"
        AMBER    = "#c8956c"
        RED      = "#c0392b"
        TXT      = "#2c2c2c"
        TXT_SEC  = "#7a7a6e"
        BORDER   = "#e8e6dd"
        FONT_SANS = "Microsoft YaHei"
        FONT_MONO = "Consolas"

        # ── 窗口基础 ──
        win = tk.Toplevel(self.root)
        win.title("GoActivity + WeRSS")
        win.geometry("460x580")
        win.resizable(False, False)
        win.configure(bg=BG)
        self._status_window = win
        win.protocol("WM_DELETE_WINDOW", self.on_status_close)

        # ── 深色顶栏 ──
        header = tk.Frame(win, bg=DARK, height=90)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="GoActivity + WeRSS",
            font=(FONT_SANS, 20, "bold"),
            fg="#ffffff", bg=DARK
        ).pack(anchor="w", padx=28, pady=(18, 0))

        tk.Label(
            header, text="校园活动知识库 · 服务管理",
            font=(FONT_SANS, 10),
            fg=AMBER, bg=DARK
        ).pack(anchor="w", padx=28)

        # ── GoActivity 服务状态 ──
        self._make_service_section(
            win, "GoActivity 服务",
            self.running, self.process, self.service_status,
            SERVICE_HOST, SERVICE_PORT,
            "/static/index.html", "/docs", "/health",
            ACCENT, BG, TXT, TXT_SEC, BORDER, RED,
            FONT_SANS, FONT_MONO, CARD_BG,
        )

        # ── WeRSS 服务状态 ──
        self._make_service_section(
            win, "WeRSS 服务",
            self.rss_running, self.rss_process, self.rss_service_status,
            RSS_HOST, RSS_PORT,
            "/", "/api/docs", "/api/docs",
            "#2980b9", BG, TXT, TXT_SEC, BORDER, RED,
            FONT_SANS, FONT_MONO, CARD_BG,
        )

        # ── 操作按钮 ──
        btn_frame = tk.Frame(win, bg=BG)
        btn_frame.pack(fill=tk.X, padx=28, pady=(16, 0))

        def make_btn(parent, text, bg_color, fg_color, cmd, side=tk.LEFT):
            b = tk.Button(
                parent, text=text,
                font=(FONT_SANS, 10, "bold"),
                bg=bg_color, fg=fg_color,
                activebackground=bg_color, activeforeground=fg_color,
                bd=0, relief="flat", cursor="hand2",
                padx=14, pady=7,
                command=cmd
            )
            hover = _lighten(bg_color, 0.15) if bg_color != BG else "#e0ddd4"
            b.bind("<Enter>", lambda e: b.configure(bg=hover))
            b.bind("<Leave>", lambda e: b.configure(bg=bg_color))
            b.pack(side=side, padx=(0, 0 if side == tk.RIGHT else 8))
            return b

        make_btn(btn_frame, "管理后台", ACCENT, "#ffffff",
                 lambda: self.open_browser())
        make_btn(btn_frame, "WeRSS 后台", "#2980b9", "#ffffff",
                 lambda: self.open_rss_browser())
        make_btn(btn_frame, "关闭", BG, TXT,
                 self.on_status_close, side=tk.RIGHT)

        win.focus_force()

    def _make_service_section(self, parent, title, is_running, process, status,
                              host, port, admin_path, docs_path, health_path,
                              accent, BG, TXT, TXT_SEC, BORDER, RED,
                              FONT_SANS, FONT_MONO, CARD_BG):
        """在状态窗口中渲染一个服务的信息区块"""
        # 分隔标题
        sec = tk.Frame(parent, bg=BG)
        sec.pack(fill=tk.X, padx=28, pady=(14, 0))
        tk.Label(sec, text=title, font=(FONT_SANS, 13, "bold"),
                 fg=TXT, bg=BG).pack(side=tk.LEFT)
        tk.Frame(sec, bg=BORDER, height=1).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0), pady=(6, 0))

        # 状态行
        bar = tk.Frame(parent, bg=BG, height=30)
        bar.pack(fill=tk.X, padx=28, pady=(6, 0))
        bar.pack_propagate(False)

        dot_c = accent if is_running else RED
        dot = tk.Canvas(bar, width=10, height=10, bg=BG, highlightthickness=0)
        dot.pack(side=tk.LEFT, pady=(0, 2))
        dot.create_oval(1, 1, 9, 9, fill=dot_c, outline=dot_c)

        status_text = "运行中" if is_running else "已停止"
        tk.Label(bar, text=f"  {status_text}",
                 font=(FONT_SANS, 11, "bold"), fg=TXT, bg=BG).pack(side=tk.LEFT)

        pid_text = f"PID  {process.pid}" if process else "PID  —"
        tk.Label(bar, text=pid_text, font=(FONT_MONO, 9),
                 fg=TXT_SEC, bg=BG).pack(side=tk.RIGHT)

        # 信息卡片
        card = tk.Frame(parent, bg=CARD_BG, highlightthickness=1,
                        highlightbackground=BORDER)
        card.pack(fill=tk.X, padx=28, pady=(4, 0))

        items = [
            ("服务地址", f"http://{host}:{port}"),
            ("管理后台", f"http://{host}:{port}{admin_path}"),
            ("API 文档", f"http://{host}:{port}{docs_path}"),
        ]
        for i, (label, value) in enumerate(items):
            row_bg = "#fafaf5" if i % 2 == 0 else CARD_BG
            row = tk.Frame(card, bg=row_bg)
            row.pack(fill=tk.X)
            tk.Label(row, text=label, font=(FONT_SANS, 9),
                     fg=TXT_SEC, bg=row_bg, width=8, anchor="w"
                     ).pack(side=tk.LEFT, padx=(12, 0), pady=6)
            tk.Label(row, text=value, font=(FONT_MONO, 9),
                     fg=TXT, bg=row_bg, anchor="w"
                     ).pack(side=tk.LEFT, padx=(0, 12), pady=6)

    def on_status_close(self):
        """关闭状态窗口（销毁并清理引用，下次打开会重建）"""
        if self._status_window is not None:
            try:
                self._status_window.destroy()
            except Exception:
                pass
            self._status_window = None

    def quit_app(self, icon=None, item=None):
        """退出应用（线程安全）"""
        self.stop_service()
        self.stop_rss_service()
        if self.icon:
            self.icon.stop()
        # 调度到主线程销毁 tkinter 并退出 mainloop
        if self.root:
            self.root.after(0, self.root.quit)

    def is_autostart_enabled(self):
        """检查是否已启用开机自启"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, AUTOSTART_REG_NAME)
            winreg.CloseKey(key)
            return True
        except WindowsError:
            return False

    def toggle_autostart(self, enable=None):
        """切换开机自启"""
        if enable is None:
            enable = not self.is_autostart_enabled()

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_SET_VALUE)
            if enable:
                pythonw = sys.executable.replace('python.exe', 'pythonw.exe')
                script_path = str(Path(__file__).absolute())
                value = f'"{pythonw}" "{script_path}"'
                winreg.SetValueEx(key, AUTOSTART_REG_NAME, 0, winreg.REG_SZ, value)
                self.show_notification("GoActivity", "已启用开机自启")
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_REG_NAME)
                except WindowsError:
                    pass
                self.show_notification("GoActivity", "已禁用开机自启")
            winreg.CloseKey(key)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"设置开机自启失败: {e}"))

    def is_rss_autostart_enabled(self):
        """检查 WeRSS 是否已启用开机自启"""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, AUTOSTART_REG_NAME_RSS)
            winreg.CloseKey(key)
            return True
        except WindowsError:
            return False

    def toggle_rss_autostart(self, enable=None):
        """切换 WeRSS 开机自启"""
        if enable is None:
            enable = not self.is_rss_autostart_enabled()

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_REG_KEY, 0, winreg.KEY_SET_VALUE)
            if enable:
                main_py = str(RSS_DIR / "main.py")
                value = f'"{self.rss_python}" "{main_py}" -job True -init True'
                winreg.SetValueEx(key, AUTOSTART_REG_NAME_RSS, 0, winreg.REG_SZ, value)
                self.show_notification("WeRSS", "已启用开机自启")
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_REG_NAME_RSS)
                except WindowsError:
                    pass
                self.show_notification("WeRSS", "已禁用开机自启")
            winreg.CloseKey(key)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"设置 WeRSS 开机自启失败: {e}"))

    def create_menu(self):
        """创建托盘菜单"""
        return pystray.Menu(
            pystray.MenuItem(
                '服务状态',
                lambda: self.show_status(),
                default=True
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                '启动 GoActivity',
                lambda: threading.Thread(target=self.start_service, daemon=True).start(),
                enabled=lambda item: not self.running
            ),
            pystray.MenuItem(
                '停止 GoActivity',
                lambda: threading.Thread(target=self.stop_service, daemon=True).start(),
                enabled=lambda item: self.running
            ),
            pystray.MenuItem(
                '重启 GoActivity',
                lambda: threading.Thread(target=self.restart_service, daemon=True).start()
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                '启动 WeRSS',
                lambda: threading.Thread(target=self.start_rss_service, daemon=True).start(),
                enabled=lambda item: not self.rss_running
            ),
            pystray.MenuItem(
                '停止 WeRSS',
                lambda: threading.Thread(target=self.stop_rss_service, daemon=True).start(),
                enabled=lambda item: self.rss_running
            ),
            pystray.MenuItem(
                '重启 WeRSS',
                lambda: threading.Thread(target=self.restart_rss_service, daemon=True).start()
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                '快捷操作',
                pystray.Menu(
                    pystray.MenuItem(
                        '触发同步',
                        lambda: threading.Thread(target=self.trigger_sync, daemon=True).start()
                    ),
                    pystray.MenuItem(
                        '发送日报',
                        lambda: threading.Thread(target=self.send_daily_report, daemon=True).start()
                    ),
                    pystray.MenuItem(
                        '发送周报',
                        lambda: threading.Thread(target=self.send_weekly_report, daemon=True).start()
                    ),
                )
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                '打开管理后台',
                lambda: self.open_browser()
            ),
            pystray.MenuItem(
                'API 文档',
                lambda: self.open_api_docs()
            ),
            pystray.MenuItem(
                '查看日志',
                lambda: self.open_logs()
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                '开机自启 (GoActivity)',
                lambda: self.toggle_autostart(),
                checked=lambda item: self.is_autostart_enabled()
            ),
            pystray.MenuItem(
                '开机自启 (WeRSS)',
                lambda: self.toggle_rss_autostart(),
                checked=lambda item: self.is_rss_autostart_enabled()
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                '退出',
                lambda: self.quit_app()
            )
        )

    def run(self):
        """运行托盘应用"""
        # 创建托盘图标
        self.icon = pystray.Icon(
            name='GoActivity',
            icon=self.icon_image,
            title='GoActivity 校园活动知识库',
            menu=self.create_menu()
        )

        # 自动启动两个服务
        threading.Thread(target=self.start_service, daemon=True).start()
        threading.Thread(target=self.start_rss_service, daemon=True).start()

        # pystray 在后台线程运行，tkinter mainloop 在主线程运行
        threading.Thread(target=self.icon.run, daemon=True).start()

        # 主线程运行 tkinter mainloop（Windows 上 tkinter 必须在主线程）
        self.root.mainloop()

        # mainloop 退出后清理
        if self.icon:
            self.icon.stop()


def main():
    """主函数"""
    # 检查是否已有实例运行
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 19876))  # 使用一个不常见的端口作为锁
    if result == 0:
        messagebox.showwarning("警告", "GoActivity 管理器已在运行")
        sys.exit(0)
    sock.close()

    # 创建并运行托盘应用
    app = GoActivityTray()
    app.run()


if __name__ == '__main__':
    main()
