"""lark-cli 可执行文件解析工具。

在 Windows 上，lark-cli 通过 .cmd 启动器分发。
subprocess 直接调用 .cmd 会遇到命令行引号问题，
因此需要解析为 node.exe + run.js 的真实调用方式。
"""

import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def is_windows_cmd_launcher(cli_path: str) -> bool:
    """判断 lark-cli 路径是否是 Windows .cmd 启动器。"""
    return Path(cli_path).name.lower() == "lark-cli.cmd"


def is_lark_cli(cli_path: str) -> bool:
    """判断路径是否是 lark-cli（任意平台变体，含 .cmd）。"""
    return Path(cli_path).name.lower() in {"lark-cli", "lark-cli.exe", "lark-cli.cmd"}


def resolve_lark_cli_run_js(cli_path: str) -> str:
    """从 lark-cli.cmd 路径解析出 node_modules 中的 run.js 绝对路径。

    Returns:
        run.js 的绝对路径字符串，找不到时返回空字符串。
    """
    cli_file = Path(cli_path)
    run_js = cli_file.parent / "node_modules" / "@larksuite" / "cli" / "scripts" / "run.js"
    return str(run_js) if run_js.exists() else ""


def build_lark_cli_command(cli_path: str) -> list[str]:
    """构建 lark-cli 的实际命令前缀。

    - 如果是 .cmd 启动器，解析为 [node, run.js]
    - 否则直接使用 cli_path

    Raises:
        RuntimeError: node 不在 PATH 中，或无法解析 run.js。
    """
    if is_windows_cmd_launcher(cli_path):
        node_path = shutil.which("node")
        run_js = resolve_lark_cli_run_js(cli_path)
        if not node_path:
            raise RuntimeError("Node.js not found in PATH for lark-cli execution.")
        if not run_js:
            raise RuntimeError("Unable to resolve lark-cli run.js path from FEISHU_CLI_PATH.")
        return [node_path, run_js]
    return [cli_path]


def run_cli_command(
    command: list[str],
    timeout: int = 60,
    parse_json: bool = True,
) -> dict[str, Any]:
    """执行 CLI 命令并返回结构化结果。

    统一的 subprocess 调用封装，消除各处重复的 subprocess.run 模式。

    Args:
        command: 命令列表
        timeout: 超时秒数
        parse_json: 是否尝试解析 stdout 为 JSON

    Returns:
        包含 return_code, stdout, stderr, data 的字典。
        data 为解析后的 JSON 对象（parse_json=True 且解析成功时），否则为 None。
    """
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    result: dict[str, Any] = {
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "data": None,
    }
    if parse_json and completed.stdout:
        try:
            result["data"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            pass
    return result
