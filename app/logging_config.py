"""结构化日志配置。

提供 JSON 格式日志（生产环境）和可读格式日志（开发环境）。
"""

import logging
import sys


def setup_logging(level: int = logging.INFO, json_format: bool = False) -> None:
    """配置全局日志。

    只配置 app 自己的 logger，不清除 uvicorn 等第三方库的 handler。

    Args:
        level: 日志级别（默认 INFO）
        json_format: 是否使用 JSON 格式（生产环境推荐）
    """
    # 只给 root logger 添加 handler（如果还没有的话）
    # 不清除已有的 handler（如 uvicorn 的）
    root = logging.getLogger()

    # 检查是否已经有我们的 handler（避免重复添加）
    if any(isinstance(h, logging.StreamHandler) and h.stream == sys.stdout for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if json_format:
        formatter = logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    handler.setFormatter(formatter)
    root.addHandler(handler)

    # 降低第三方库日志级别
    for noisy in ("httpx", "httpcore", "urllib3", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
