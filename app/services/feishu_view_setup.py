"""Feishu Bitable 视图自动设置服务。

通过 lark-cli 自动创建和配置飞书多维表格视图。
幂等：运行前先 GET 视图列表，存在则跳过。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.utils.lark_cli import build_lark_cli_command, run_cli_command

logger = logging.getLogger(__name__)


@dataclass
class ViewConfig:
    """视图配置"""
    name: str
    type: str = "grid"  # grid | kanban | calendar | gantt | gallery
    filter_config: dict[str, Any] | None = None
    sort_config: dict[str, Any] | None = None
    group_config: dict[str, Any] | None = None
    visible_fields: list[str] | None = None


# 视图配置列表（11 个视图，按使用频率排序）
# 合并讲座/演出/比赛/招新为「分类浏览」，新增「活动归档」视图
VIEW_CONFIGS: list[ViewConfig] = [
    # 1. 本周活动 — 最常用的日程视图
    ViewConfig(
        name="本周活动",
        type="grid",
        filter_config={
            "logic": "and",
            "conditions": [
                ["时间状态", "is", "upcoming"],
                ["状态", "is not", "ignored_non_event"],
                ["状态", "is not", "archived"],
                ["保留决策", "is not", "keep_recap_lowest"],
            ],
        },
        sort_config={
            "sort_config": [{"field": "开始时间", "desc": False}],
        },
        visible_fields=[
            "标题", "活动类型", "一级分类", "开始时间", "结束时间",
            "活动地点", "嘉宾", "主办方", "报名方式", "标签", "海报附件",
        ],
    ),
    # 2. 活动总表 — 默认全量视图
    ViewConfig(
        name="活动总表",
        type="grid",
        filter_config={
            "logic": "and",
            "conditions": [
                ["保留决策", "is not", "keep_recap_lowest"],
                ["保留决策", "is not", "drop_past_event"],
                ["时间状态", "is not", "expired"],
                ["状态", "is not", "ignored_non_event"],
                ["状态", "is not", "archived"],
            ],
        },
        sort_config={
            "sort_config": [{"field": "开始时间", "desc": False}],
        },
        visible_fields=[
            "标题", "活动类型", "一级分类", "二级分类",
            "开始时间", "结束时间", "活动地点", "嘉宾", "主办方",
            "报名方式", "标签", "状态", "时间状态", "保留决策",
            "用户置顶", "置信度", "海报附件", "公众号",
            "关联原因", "摘要", "更新时间",
        ],
    ),
    # 3. 用户置顶
    ViewConfig(
        name="用户置顶",
        type="grid",
        filter_config={
            "logic": "and",
            "conditions": [
                ["用户置顶", "is", True],
                ["状态", "is not", "archived"],
            ],
        },
        sort_config={
            "sort_config": [{"field": "开始时间", "desc": False}],
        },
        visible_fields=[
            "标题", "活动类型", "开始时间", "地点", "嘉宾",
            "主办方", "报名方式", "原文链接", "海报附件", "状态", "更新时间",
        ],
    ),
    # 4. 活动日历（Calendar）
    ViewConfig(
        name="活动日历",
        type="calendar",
        filter_config={
            "logic": "and",
            "conditions": [
                ["状态", "is not", "failed_sync"],
                ["状态", "is not", "ignored_non_event"],
                ["状态", "is not", "archived"],
                ["时间状态", "is not", "expired"],
                ["时间状态", "is not", "past"],
            ],
        },
    ),
    # 5. 待审核看板（Kanban）
    ViewConfig(
        name="待审核看板",
        type="kanban",
        filter_config={
            "logic": "and",
            "conditions": [
                ["用户置顶", "==", False],
                ["状态", "is not", "archived"],
            ],
        },
        group_config={
            "group_config": [{"field": "状态", "desc": False}],
        },
    ),
    # 6. 分类浏览 — 合并讲座/演出/比赛/招新，按活动类型分组
    ViewConfig(
        name="分类浏览",
        type="grid",
        filter_config={
            "logic": "and",
            "conditions": [
                ["时间状态", "is not", "expired"],
                ["保留决策", "is not", "keep_recap_lowest"],
                ["状态", "is not", "ignored_non_event"],
                ["状态", "is not", "archived"],
            ],
        },
        group_config={
            "group_config": [{"field": "活动类型", "desc": False}],
        },
        sort_config={
            "sort_config": [{"field": "开始时间", "desc": False}],
        },
        visible_fields=[
            "标题", "活动类型", "一级分类", "开始时间", "结束时间",
            "活动地点", "嘉宾", "主办方", "报名方式", "标签",
            "时间状态", "海报附件",
        ],
    ),
    # 7. 按公众号分组
    ViewConfig(
        name="按公众号分组",
        type="grid",
        filter_config={
            "logic": "and",
            "conditions": [
                ["状态", "is not", "ignored_non_event"],
                ["状态", "is not", "archived"],
                ["保留决策", "is not", "keep_recap_lowest"],
            ],
        },
        group_config={
            "group_config": [{"field": "公众号", "desc": False}],
        },
        sort_config={
            "sort_config": [{"field": "开始时间", "desc": False}],
        },
        visible_fields=[
            "标题", "活动类型", "一级分类", "开始时间", "活动地点",
            "嘉宾", "主办方", "标签", "状态", "时间状态", "置信度",
        ],
    ),
    # 8. 失败排查
    ViewConfig(
        name="失败排查",
        type="grid",
        filter_config={
            "logic": "or",
            "conditions": [
                ["状态", "is", "failed_extract"],
                ["状态", "is", "failed_sync"],
            ],
        },
        sort_config={
            "sort_config": [{"field": "更新时间", "desc": True}],
        },
        visible_fields=[
            "标题", "状态", "活动类型", "保留决策", "关联原因",
            "置信度", "原文链接", "更新时间", "公众号",
        ],
    ),
    # 9. 已过期
    ViewConfig(
        name="已过期",
        type="grid",
        filter_config={
            "logic": "and",
            "conditions": [
                ["时间状态", "is", "expired"],
                ["状态", "is not", "archived"],
            ],
        },
        sort_config={
            "sort_config": [{"field": "开始时间", "desc": True}],
        },
    ),
    # 10. 待确认时间
    ViewConfig(
        name="待确认时间",
        type="grid",
        filter_config={
            "logic": "and",
            "conditions": [
                ["时间状态", "is", "unknown"],
                ["状态", "is not", "archived"],
            ],
        },
        sort_config={
            "sort_config": [{"field": "更新时间", "desc": True}],
        },
    ),
    # 11. 活动归档 — 归档视图，只显示基础信息
    ViewConfig(
        name="活动归档",
        type="grid",
        filter_config={
            "logic": "and",
            "conditions": [
                ["状态", "is", "archived"],
            ],
        },
        sort_config={
            "sort_config": [{"field": "归档时间", "desc": True}],
        },
        visible_fields=[
            "标题", "一级分类", "开始时间", "结束时间", "活动地点",
            "主办方", "公众号", "原文链接", "归档时间",
        ],
    ),
]


@dataclass
class ViewSetupResult:
    """单个视图的设置结果"""
    name: str
    action: str  # created | skipped | failed
    view_id: str = ""
    error: str = ""


@dataclass
class SetupAllResult:
    """全部视图设置结果"""
    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[ViewSetupResult] = field(default_factory=list)


class FeishuViewSetupService:
    """Feishu Bitable 视图自动设置服务"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._command_prefix: list[str] = self._build_command_prefix()

    def _build_command_prefix(self) -> list[str]:
        """构建 lark-cli 命令前缀"""
        return build_lark_cli_command(self.settings.feishu_cli_path)

    def _run_cli(self, command: list[str]) -> dict[str, Any]:
        """执行 lark-cli 命令并返回 JSON 结果"""
        result = run_cli_command(command, timeout=60)
        if result["return_code"] != 0:
            raise RuntimeError(f"lark-cli failed (rc={result['return_code']}): {result['stderr'] or result['stdout']}")
        return result["data"] or {"raw": result["stdout"]}

    def list_views(self) -> dict[str, str]:
        """获取现有视图列表，返回 {视图名: 视图ID}"""
        command = [
            *self._command_prefix,
            "base",
            "+view-list",
            "--as", self.settings.feishu_cli_as,
            "--base-token", self.settings.feishu_bitable_app_token,
            "--table-id", self.settings.feishu_bitable_table_id,
            "--format", "json",
        ]
        data = self._run_cli(command)
        views = data.get("data", {}).get("views", [])
        return {v["name"]: v["id"] for v in views}

    def create_view(self, config: ViewConfig) -> str:
        """创建单个视图，返回 view_id"""
        payload = {"name": config.name, "type": config.type}
        command = [
            *self._command_prefix,
            "base",
            "+view-create",
            "--as", self.settings.feishu_cli_as,
            "--base-token", self.settings.feishu_bitable_app_token,
            "--table-id", self.settings.feishu_bitable_table_id,
            "--json", json.dumps(payload, ensure_ascii=False),
            "--format", "json",
        ]
        data = self._run_cli(command)
        view_id = data.get("data", {}).get("view", {}).get("view_id", "")
        if not view_id:
            raise RuntimeError(f"Failed to get view_id from response: {data}")
        return view_id

    def set_filter(self, view_id: str, config: dict[str, Any]) -> None:
        """设置视图过滤条件"""
        command = [
            *self._command_prefix,
            "base",
            "+view-set-filter",
            "--as", self.settings.feishu_cli_as,
            "--base-token", self.settings.feishu_bitable_app_token,
            "--table-id", self.settings.feishu_bitable_table_id,
            "--view-id", view_id,
            "--json", json.dumps(config, ensure_ascii=False),
            "--format", "json",
        ]
        self._run_cli(command)

    def set_sort(self, view_id: str, config: dict[str, Any]) -> None:
        """设置视图排序"""
        command = [
            *self._command_prefix,
            "base",
            "+view-set-sort",
            "--as", self.settings.feishu_cli_as,
            "--base-token", self.settings.feishu_bitable_app_token,
            "--table-id", self.settings.feishu_bitable_table_id,
            "--view-id", view_id,
            "--json", json.dumps(config, ensure_ascii=False),
            "--format", "json",
        ]
        self._run_cli(command)

    def set_group(self, view_id: str, config: dict[str, Any]) -> None:
        """设置视图分组（仅 kanban/gantt）"""
        command = [
            *self._command_prefix,
            "base",
            "+view-set-group",
            "--as", self.settings.feishu_cli_as,
            "--base-token", self.settings.feishu_bitable_app_token,
            "--table-id", self.settings.feishu_bitable_table_id,
            "--view-id", view_id,
            "--json", json.dumps(config, ensure_ascii=False),
            "--format", "json",
        ]
        self._run_cli(command)

    def set_visible_fields(self, view_id: str, fields: list[str]) -> None:
        """设置视图可见字段"""
        config = {"visible_fields": fields}
        command = [
            *self._command_prefix,
            "base",
            "+view-set-visible-fields",
            "--as", self.settings.feishu_cli_as,
            "--base-token", self.settings.feishu_bitable_app_token,
            "--table-id", self.settings.feishu_bitable_table_id,
            "--view-id", view_id,
            "--json", json.dumps(config, ensure_ascii=False),
            "--format", "json",
        ]
        self._run_cli(command)

    def setup_view(self, config: ViewConfig, existing_views: dict[str, str]) -> ViewSetupResult:
        """设置单个视图（幂等）"""
        # 如果视图已存在，更新配置
        if config.name in existing_views:
            view_id = existing_views[config.name]
            logger.info("View %r already exists (id=%s), updating config", config.name, view_id)
            try:
                self._apply_view_config(view_id, config)
                return ViewSetupResult(name=config.name, action="updated", view_id=view_id)
            except Exception as exc:
                logger.error("Failed to update view %r: %s", config.name, exc)
                return ViewSetupResult(name=config.name, action="failed", view_id=view_id, error=str(exc))

        try:
            view_id = self.create_view(config)
            logger.info("Created view %r (id=%s)", config.name, view_id)
            self._apply_view_config(view_id, config)
            return ViewSetupResult(name=config.name, action="created", view_id=view_id)
        except Exception as exc:
            logger.error("Failed to setup view %r: %s", config.name, exc)
            return ViewSetupResult(name=config.name, action="failed", error=str(exc))

    def _apply_view_config(self, view_id: str, config: ViewConfig) -> None:
        """应用视图配置（过滤、排序、分组、可见字段）"""
        # 设置过滤条件
        if config.filter_config:
            self.set_filter(view_id, config.filter_config)
            logger.debug("Set filter for view %r", config.name)

        # 设置排序
        if config.sort_config:
            self.set_sort(view_id, config.sort_config)
            logger.debug("Set sort for view %r", config.name)

        # 设置分组
        if config.group_config:
            self.set_group(view_id, config.group_config)
            logger.debug("Set group for view %r", config.name)

        # 设置可见字段
        if config.visible_fields:
            self.set_visible_fields(view_id, config.visible_fields)
            logger.debug("Set visible fields for view %r", config.name)

    def setup_all_views(self, configs: list[ViewConfig] | None = None) -> SetupAllResult:
        """批量设置所有视图（幂等）"""
        if configs is None:
            configs = VIEW_CONFIGS

        # 获取现有视图
        existing_views = self.list_views()
        logger.info("Found %d existing views: %s", len(existing_views), list(existing_views.keys()))

        result = SetupAllResult(total=len(configs))

        for config in configs:
            view_result = self.setup_view(config, existing_views)
            result.results.append(view_result)

            if view_result.action == "created":
                result.created += 1
            elif view_result.action == "updated":
                result.updated += 1
            elif view_result.action == "skipped":
                result.skipped += 1
            else:
                result.failed += 1

        logger.info(
            "View setup complete: %d total, %d created, %d updated, %d skipped, %d failed",
            result.total, result.created, result.updated, result.skipped, result.failed,
        )
        return result


