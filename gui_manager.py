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
    from PIL import Image, ImageDraw
    import tkinter as tk
    from tkinter import messagebox
except ImportError as e:
    print(f"缺少依赖: {e}")
    print("请运行: pip install pystray pillow")
    sys.exit(1)

# 常量
SERVICE_PORT = 8000
SERVICE_HOST = "127.0.0.1"
AUTOSTART_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_REG_NAME = "GoActivity"


class GoActivityTray:
    """GoActivity 系统托盘管理器"""

    def __init__(self):
        self.process = None
        self.running = False
        self.icon = None
        self.root = None
        self.service_status = "unknown"

        # 创建日志目录
        os.makedirs('logs', exist_ok=True)

        # 创建图标
        self.icon_image = self.create_icon()

    def create_icon(self, color='gray'):
        """创建托盘图标"""
        # 尝试加载自定义图标
        icon_path = Path(__file__).parent / 'app_icon.ico'
        if icon_path.exists():
            try:
                # 加载自定义图标
                base_image = Image.open(icon_path)
                # 调整大小为 64x64
                base_image = base_image.resize((64, 64), Image.Resampling.LANCZOS)

                # 根据状态添加颜色叠加
                if color == 'green':
                    # 绿色 - 运行中
                    overlay_color = (76, 175, 80, 100)
                elif color == 'red':
                    # 红色 - 已停止
                    overlay_color = (244, 67, 54, 100)
                else:
                    # 灰色 - 未知
                    overlay_color = (158, 158, 158, 100)

                # 创建叠加层
                overlay = Image.new('RGBA', base_image.size, overlay_color)
                # 混合图像
                result = Image.alpha_composite(base_image.convert('RGBA'), overlay)

                # 添加状态指示器
                draw = ImageDraw.Draw(result)
                indicator_radius = 8
                indicator_x = 64 - indicator_radius - 4
                indicator_y = 64 - indicator_radius - 4

                if color == 'green':
                    indicator_color = (76, 175, 80, 255)
                elif color == 'red':
                    indicator_color = (244, 67, 54, 255)
                else:
                    indicator_color = (158, 158, 158, 255)

                # 绘制状态指示器
                draw.ellipse(
                    [(indicator_x - indicator_radius, indicator_y - indicator_radius),
                     (indicator_x + indicator_radius, indicator_y + indicator_radius)],
                    fill=indicator_color,
                    outline=(255, 255, 255, 200),
                    width=2
                )

                return result
            except Exception as e:
                print(f"Failed to load custom icon: {e}")

        # 如果没有自定义图标或加载失败，使用默认图标
        width = 64
        height = 64
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # 绘制圆形背景
        if color == 'green':
            fill_color = (76, 175, 80, 255)  # 绿色 - 运行中
        elif color == 'red':
            fill_color = (244, 67, 54, 255)  # 红色 - 已停止
        else:
            fill_color = (158, 158, 158, 255)  # 灰色 - 未知

        # 绘制圆角矩形
        draw.rounded_rectangle(
            [(4, 4), (width - 4, height - 4)],
            radius=12,
            fill=fill_color
        )

        # 绘制文字 "GA"
        draw.text(
            (width // 2, height // 2),
            "GA",
            fill='white',
            anchor='mm',
            align='center'
        )

        return image

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
            messagebox.showerror("错误", f"启动服务失败: {e}")

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

    def update_icon(self, color):
        """更新托盘图标"""
        if self.icon:
            self.icon_image = self.create_icon(color)
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
        """显示服务状态窗口"""
        if self.root is None:
            self.root = tk.Tk()
            self.root.title("GoActivity 服务状态")
            self.root.geometry("450x350")
            self.root.resizable(False, False)

            # 状态标签
            status_text = "运行中" if self.running else "已停止"
            status_color = "green" if self.running else "red"

            tk.Label(
                self.root,
                text=f"服务状态: {status_text}",
                font=("Arial", 14),
                fg=status_color
            ).pack(pady=10)

            # 信息文本
            info_text = f"""
服务地址: http://{SERVICE_HOST}:{SERVICE_PORT}
管理后台: http://{SERVICE_HOST}:{SERVICE_PORT}/
API 文档: http://{SERVICE_HOST}:{SERVICE_PORT}/docs
健康检查: http://{SERVICE_HOST}:{SERVICE_PORT}/health

进程 ID: {self.process.pid if self.process else 'N/A'}
            """.strip()

            tk.Label(
                self.root,
                text=info_text,
                font=("Consolas", 10),
                justify=tk.LEFT
            ).pack(pady=10)

            # 按钮框架
            btn_frame = tk.Frame(self.root)
            btn_frame.pack(pady=10)

            tk.Button(
                btn_frame,
                text="打开管理后台",
                command=self.open_browser
            ).pack(side=tk.LEFT, padx=5)

            tk.Button(
                btn_frame,
                text="API 文档",
                command=self.open_api_docs
            ).pack(side=tk.LEFT, padx=5)

            tk.Button(
                btn_frame,
                text="查看日志",
                command=self.open_logs
            ).pack(side=tk.LEFT, padx=5)

            tk.Button(
                btn_frame,
                text="关闭",
                command=self.root.destroy
            ).pack(side=tk.LEFT, padx=5)

            # 关闭窗口时重置 root
            self.root.protocol("WM_DELETE_WINDOW", self.on_status_close)

        self.root.deiconify()
        self.root.lift()

    def on_status_close(self):
        """关闭状态窗口"""
        if self.root:
            self.root.withdraw()

    def quit_app(self, icon=None, item=None):
        """退出应用"""
        self.stop_service()
        if self.icon:
            self.icon.stop()
        if self.root:
            self.root.destroy()
        sys.exit(0)

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
                # 获取 pythonw.exe 路径
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
            messagebox.showerror("错误", f"设置开机自启失败: {e}")

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
                '启动服务',
                lambda: threading.Thread(target=self.start_service, daemon=True).start(),
                enabled=lambda item: not self.running
            ),
            pystray.MenuItem(
                '停止服务',
                lambda: threading.Thread(target=self.stop_service, daemon=True).start(),
                enabled=lambda item: self.running
            ),
            pystray.MenuItem(
                '重启服务',
                lambda: threading.Thread(target=self.restart_service, daemon=True).start()
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
                '开机自启',
                lambda: self.toggle_autostart(),
                checked=lambda item: self.is_autostart_enabled()
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

        # 自动启动服务
        threading.Thread(target=self.start_service, daemon=True).start()

        # 运行托盘图标
        self.icon.run()


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
