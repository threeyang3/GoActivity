"""项目统一异常体系。

层级：
  AppError
  ├── ProviderError      — Vision/OCR provider 调用失败
  ├── FeishuError        — 飞书同步/消息发送失败
  ├── SyncError          — 数据同步失败（we-mp-rss 拉取等）
  └── ValidationError    — 数据校验失败（抽取结果不合法等）
"""


class AppError(Exception):
    """项目基础异常。所有业务异常的基类。"""

    def __init__(self, message: str = "", *, cause: Exception | None = None) -> None:
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause


class ProviderError(AppError):
    """Vision/OCR provider 调用失败（API 不可用、返回非法 JSON 等）。"""


class FeishuError(AppError):
    """飞书同步失败（lark-cli 执行失败、OpenAPI 错误等）。"""


class SyncError(AppError):
    """数据同步失败（we-mp-rss 拉取超时、解析错误等）。"""


class ValidationError(AppError):
    """数据校验失败（抽取结果字段不合法、时间格式错误等）。"""
