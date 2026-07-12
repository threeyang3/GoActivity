"""API 鉴权依赖。

本地访问（127.0.0.1）不需要 token。
局域网访问（allow_lan_access=True）必须配置 admin_token。
"""

import logging
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


def _is_local_request(request: Request) -> bool:
    """判断请求是否来自本机。"""
    client = request.client
    if client is None:
        # TestClient or no client info — treat as local
        return True
    host = client.host
    return host in ("127.0.0.1", "::1", "localhost", "testclient", "testserver")


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """写接口鉴权依赖。

    规则：
    - 本机访问：不需要 token（低摩擦）
    - 局域网访问：必须提供有效 admin_token
    - 未配置 admin_token 时不允许局域网访问
    """
    settings = get_settings()

    # 本机访问放行
    if _is_local_request(request):
        return

    # 局域网访问必须开启 allow_lan_access
    if not settings.allow_lan_access:
        raise HTTPException(
            status_code=403,
            detail="局域网访问未启用。请在配置中设置 allow_lan_access=true 并配置 admin_token。",
        )

    # 局域网访问必须配置 admin_token
    if not settings.admin_token:
        raise HTTPException(
            status_code=503,
            detail="服务未配置管理令牌，无法处理局域网请求。",
        )

    # 验证 token
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="缺少认证凭据。请在 Authorization 头中提供 Bearer token。",
        )

    if credentials.credentials != settings.admin_token:
        logger.warning("Invalid admin token attempt from %s", request.client.host if request.client else "unknown")
        raise HTTPException(status_code=401, detail="认证凭据无效。")
