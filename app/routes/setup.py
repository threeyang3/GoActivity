"""飞书视图设置路由。"""

from fastapi import APIRouter

from app.schemas import FeishuViewSetupResponse, ViewSetupResultItem
from app.services.feishu_view_setup import FeishuViewSetupService

router = APIRouter(tags=["setup"])


@router.post("/setup/feishu-views", response_model=FeishuViewSetupResponse)
def setup_feishu_views() -> FeishuViewSetupResponse:
    """自动设置飞书 Bitable 视图（幂等）"""
    service = FeishuViewSetupService()
    result = service.setup_all_views()
    return FeishuViewSetupResponse(
        total=result.total,
        created=result.created,
        updated=result.updated,
        skipped=result.skipped,
        failed=result.failed,
        results=[
            ViewSetupResultItem(
                name=r.name,
                action=r.action,
                view_id=r.view_id,
                error=r.error,
            )
            for r in result.results
        ],
    )
