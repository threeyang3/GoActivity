"""
GoActivity 服务启动脚本
支持命令行参数控制启动方式
"""

import argparse
import logging
import os
import sys
import signal
import subprocess
import time
import socket
from pathlib import Path

# 设置工作目录为脚本所在目录
os.chdir(Path(__file__).parent)

# 创建日志目录
os.makedirs('logs', exist_ok=True)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/service.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def check_port_available(host, port):
    """检查端口是否可用"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        return False


def check_dependencies():
    """检查依赖是否安装"""
    required = ['fastapi', 'uvicorn', 'sqlalchemy', 'pydantic']
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        logger.error(f"缺少依赖: {', '.join(missing)}")
        logger.error("请运行: pip install -r requirements.txt")
        return False
    return True


def check_env_file():
    """检查配置文件"""
    env_path = Path('.env')
    env_example = Path('.env.example')

    if not env_path.exists():
        if env_example.exists():
            logger.warning(".env 文件不存在，正在从 .env.example 创建...")
            import shutil
            shutil.copy(env_example, env_path)
            logger.info("已创建 .env 文件，请根据需要修改配置")
        else:
            logger.warning(".env 文件不存在，将使用默认配置")
    return True


class GoActivityService:
    """GoActivity 服务管理器"""

    def __init__(self):
        self.process = None
        self.running = False
        # 确保日志目录存在
        os.makedirs('logs', exist_ok=True)

    def start(self, host='127.0.0.1', port=8000, workers=1):
        """启动服务"""
        logger.info(f"正在启动 GoActivity 服务... ({host}:{port})")

        # 检查端口
        if not check_port_available(host, port):
            logger.error(f"端口 {port} 已被占用，请先停止占用该端口的程序")
            return False

        # 检查依赖
        if not check_dependencies():
            return False

        # 检查配置文件
        check_env_file()

        # 构建 uvicorn 命令
        cmd = [
            sys.executable, '-m', 'uvicorn',
            'app.main:app',
            '--host', host,
            '--port', str(port),
            '--workers', str(workers),
            '--log-level', 'info',
            '--access-log',
        ]

        try:
            # 启动 uvicorn 进程
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            self.running = True
            logger.info(f"GoActivity 服务已启动 (PID: {self.process.pid})")
            logger.info(f"管理后台: http://{host}:{port}/")
            logger.info(f"API 文档: http://{host}:{port}/docs")
            return True
        except Exception as e:
            logger.error(f"启动服务失败: {e}")
            return False

    def stop(self):
        """停止服务"""
        if self.process and self.running:
            logger.info("正在停止 GoActivity 服务...")
            self.running = False

            # 发送终止信号
            if sys.platform == 'win32':
                self.process.terminate()
            else:
                self.process.send_signal(signal.SIGTERM)

            # 等待进程结束
            try:
                self.process.wait(timeout=10)
                logger.info("GoActivity 服务已停止")
            except subprocess.TimeoutExpired:
                logger.warning("服务未响应，强制终止...")
                self.process.kill()
                self.process.wait()

    def run_forever(self, host='127.0.0.1', port=8000):
        """持续运行服务（阻塞）"""
        if not self.start(host, port):
            return False

        # 注册信号处理
        def signal_handler(signum, frame):
            logger.info("收到停止信号...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # 等待进程结束
        try:
            while self.running:
                if self.process.poll() is not None:
                    logger.error(f"服务意外停止 (退出码: {self.process.returncode})")
                    self.running = False
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

        return True


def main():
    parser = argparse.ArgumentParser(description='GoActivity 服务管理')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址 (默认: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8000, help='监听端口 (默认: 8000)')
    parser.add_argument('--install', action='store_true', help='安装为 Windows 服务')
    parser.add_argument('--uninstall', action='store_true', help='卸载 Windows 服务')
    parser.add_argument('--start', action='store_true', help='启动服务')
    parser.add_argument('--stop', action='store_true', help='停止服务')
    parser.add_argument('--status', action='store_true', help='查看服务状态')

    args = parser.parse_args()

    service = GoActivityService()

    if args.install:
        # 安装为 Windows 服务
        install_service()
    elif args.uninstall:
        # 卸载 Windows 服务
        uninstall_service()
    elif args.start:
        # 启动服务
        service.run_forever(args.host, args.port)
    elif args.stop:
        # 停止服务
        service.stop()
    elif args.status:
        # 查看状态
        show_status()
    else:
        # 默认启动服务
        service.run_forever(args.host, args.port)


def install_service():
    """安装为 Windows 服务"""
    if sys.platform != 'win32':
        logger.error("Windows 服务仅支持 Windows 系统")
        return

    # 检查 NSSM 是否存在
    nssm_path = find_nssm()
    if not nssm_path:
        logger.error("未找到 NSSM，请先下载 NSSM 并放置到系统 PATH 中")
        logger.info("下载地址: https://nssm.cc/download")
        return

    service_name = "GoActivity"
    script_path = Path(__file__).absolute()
    python_path = sys.executable

    # 安装服务
    cmd = [
        nssm_path, 'install', service_name,
        python_path,
        f'"{script_path}" --start --host 0.0.0.0 --port 8000'
    ]

    try:
        subprocess.run(cmd, check=True)
        logger.info(f"服务 '{service_name}' 安装成功")

        # 配置服务
        configure_service(nssm_path, service_name)
    except subprocess.CalledProcessError as e:
        logger.error(f"安装服务失败: {e}")


def configure_service(nssm_path, service_name):
    """配置服务参数"""
    configs = {
        'DisplayName': 'GoActivity 校园活动知识库服务',
        'Description': 'GoActivity - 校园活动采集、处理和飞书同步服务',
        'Start': 'SERVICE_AUTO_START',  # 开机自启
        'AppDirectory': str(Path(__file__).parent),
        'AppStdout': str(Path(__file__).parent / 'logs' / 'service_stdout.log'),
        'AppStderr': str(Path(__file__).parent / 'logs' / 'service_stderr.log'),
        'AppRotateFiles': '1',
        'AppRotateBytes': '10485760',  # 10MB
    }

    for key, value in configs.items():
        cmd = [nssm_path, 'set', service_name, key, value]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.warning(f"配置 {key} 失败")

    logger.info("服务配置完成")


def uninstall_service():
    """卸载 Windows 服务"""
    if sys.platform != 'win32':
        logger.error("Windows 服务仅支持 Windows 系统")
        return

    nssm_path = find_nssm()
    if not nssm_path:
        logger.error("未找到 NSSM")
        return

    service_name = "GoActivity"

    # 先停止服务
    try:
        subprocess.run([nssm_path, 'stop', service_name], capture_output=True)
    except Exception:
        pass

    # 卸载服务
    try:
        subprocess.run([nssm_path, 'remove', service_name, 'confirm'], check=True)
        logger.info(f"服务 '{service_name}' 已卸载")
    except subprocess.CalledProcessError as e:
        logger.error(f"卸载服务失败: {e}")


def show_status():
    """显示服务状态"""
    if sys.platform != 'win32':
        logger.error("Windows 服务仅支持 Windows 系统")
        return

    nssm_path = find_nssm()
    if not nssm_path:
        logger.error("未找到 NSSM")
        return

    service_name = "GoActivity"

    try:
        result = subprocess.run(
            [nssm_path, 'status', service_name],
            capture_output=True,
            text=True
        )
        print(f"服务状态: {result.stdout.strip()}")
    except Exception:
        print("服务未安装或无法获取状态")


def find_nssm():
    """查找 NSSM 可执行文件"""
    # 检查 PATH 中是否存在
    import shutil
    nssm = shutil.which('nssm')
    if nssm:
        return nssm

    # 检查常见位置
    common_paths = [
        Path('C:/nssm/nssm.exe'),
        Path('C:/Program Files/nssm/nssm.exe'),
        Path.home() / 'nssm' / 'nssm.exe',
    ]

    for path in common_paths:
        if path.exists():
            return str(path)

    return None


if __name__ == '__main__':
    main()
