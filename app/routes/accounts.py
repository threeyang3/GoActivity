"""公众号管理代理路由。

转发 GoActivity 前端请求到 we-mp-rss 的 /mps API。
"""

import logging

import requests as http_requests
from fastapi import APIRouter, HTTPException, Query

from fastapi import Depends

from app.auth import require_admin
from app.config import get_settings

router = APIRouter(prefix="/accounts", tags=["accounts"])
logger = logging.getLogger(__name__)


def _rss_base() -> str:
    s = get_settings()
    return f"{s.we_mp_rss_base_url}{s.we_mp_rss_api_base}/mps"


def _auth_headers() -> dict[str, str]:
    s = get_settings()
    ak = s.we_mp_rss_access_key.strip()
    sk = s.we_mp_rss_secret_key.strip()
    if not ak or not sk:
        raise HTTPException(status_code=500, detail="WE_MP_RSS_ACCESS_KEY / SECRET_KEY 未配置")
    return {"Authorization": f"AK-SK {ak}:{sk}"}


def _proxy_error(e: Exception) -> HTTPException:
    """将 requests 异常转为 HTTPException。HTTPException 直接透传。"""
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, http_requests.HTTPError):
        resp = e.response
        status = resp.status_code if resp is not None else 502
        try:
            detail = resp.json() if resp is not None else str(e)
        except Exception:
            detail = resp.text if resp is not None else str(e)
        return HTTPException(status_code=min(status, 599), detail=detail)
    return HTTPException(status_code=502, detail=f"we-mp-rss 不可达: {e}")


@router.get("")
def list_accounts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    kw: str = Query(""),
    status: int | None = Query(None),
):
    """列出已订阅公众号。"""
    params: dict = {"limit": limit, "offset": offset}
    if kw:
        params["kw"] = kw
    if status is not None:
        params["status"] = status
    try:
        resp = http_requests.get(
            _rss_base(), params=params, headers=_auth_headers(), timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise _proxy_error(e)


@router.get("/search/{kw}")
def search_accounts(kw: str, limit: int = 10, offset: int = 0):
    """搜索公众号（微信搜索）。"""
    try:
        resp = http_requests.get(
            f"{_rss_base()}/search/{kw}",
            params={"limit": limit, "offset": offset},
            headers=_auth_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise _proxy_error(e)


@router.post("")
def add_account(body: dict, _auth: None = Depends(require_admin)):
    """添加公众号。需要搜索结果中的 mp_id、mp_name、avatar 等字段。"""
    try:
        resp = http_requests.post(
            _rss_base(), json=body, headers=_auth_headers(), timeout=60
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise _proxy_error(e)


@router.delete("/{mp_id}")
def delete_account(mp_id: str, _auth: None = Depends(require_admin)):
    """删除公众号。"""
    try:
        resp = http_requests.delete(
            f"{_rss_base()}/{mp_id}", headers=_auth_headers(), timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise _proxy_error(e)


@router.post("/update/{mp_id}")
def update_account_articles(mp_id: str, _auth: None = Depends(require_admin)):
    """触发公众号文章更新。"""
    try:
        resp = http_requests.get(
            f"{_rss_base()}/update/{mp_id}", headers=_auth_headers(), timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise _proxy_error(e)
