from types import SimpleNamespace

from app.db import init_db
from app.services.feishu_view_setup import (
    FeishuViewSetupService,
    ViewConfig,
    VIEW_CONFIGS,
)
from app.utils.lark_cli import is_windows_cmd_launcher, resolve_lark_cli_run_js


def test_view_configs_cover_all_13_views() -> None:
    """视图配置覆盖 13 个视图"""
    assert len(VIEW_CONFIGS) == 13
    names = [v.name for v in VIEW_CONFIGS]
    expected = [
        "活动日历", "待审核看板", "活动总表", "用户置顶", "招新与志愿者",
        "讲座", "演出与放映", "比赛与征稿", "失败排查", "已过期", "待确认时间",
        "按公众号分组", "本周活动",
    ]
    assert names == expected


def test_view_configs_have_correct_types() -> None:
    """每个视图类型正确"""
    type_map = {v.name: v.type for v in VIEW_CONFIGS}
    assert type_map["活动日历"] == "calendar"
    assert type_map["待审核看板"] == "kanban"
    # 其余都是 grid
    for name in ["活动总表", "用户置顶", "招新与志愿者", "讲座", "演出与放映", "比赛与征稿", "失败排查", "已过期", "待确认时间", "按公众号分组", "本周活动"]:
        assert type_map[name] == "grid", f"{name} should be grid"


def test_view_configs_have_filter_where_expected() -> None:
    """需要过滤的视图都有 filter_config"""
    views_with_filter = {
        "活动日历", "待审核看板", "用户置顶", "招新与志愿者", "讲座",
        "演出与放映", "比赛与征稿", "失败排查", "已过期", "待确认时间",
        "活动总表", "按公众号分组", "本周活动",
    }
    for config in VIEW_CONFIGS:
        if config.name in views_with_filter:
            assert config.filter_config is not None, f"{config.name} should have filter"
        else:
            assert config.filter_config is None, f"{config.name} should not have filter"


def test_view_configs_have_sort_where_expected() -> None:
    """Grid 视图都有 sort_config（除了活动日历和待审核看板）"""
    views_without_sort = {"活动日历", "待审核看板"}
    for config in VIEW_CONFIGS:
        if config.name in views_without_sort:
            assert config.sort_config is None, f"{config.name} should not have sort"
        else:
            assert config.sort_config is not None, f"{config.name} should have sort"


def test_kanban_view_has_group_config() -> None:
    """看板视图有 group_config"""
    kanban = next(v for v in VIEW_CONFIGS if v.name == "待审核看板")
    assert kanban.group_config is not None
    assert kanban.group_config["group_config"][0]["field"] == "状态"


def test_setup_view_updates_existing(monkeypatch) -> None:
    """已存在的视图会更新配置"""
    service = FeishuViewSetupService()

    # Mock lark-cli
    def mock_run(command, **kwargs):
        cmd_str = " ".join(command)
        if "+view-set-filter" in cmd_str or "+view-set-sort" in cmd_str or "+view-set-visible-fields" in cmd_str:
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("app.services.feishu_view_setup.subprocess.run", mock_run)

    config = ViewConfig(
        name="活动总表",
        type="grid",
        filter_config={"logic": "and", "conditions": [["状态", "is not", "ignored"]]},
    )
    existing_views = {"活动总表": "view-123"}

    result = service.setup_view(config, existing_views)
    assert result.action == "updated"
    assert result.view_id == "view-123"


def test_setup_view_creates_new(monkeypatch) -> None:
    """新视图被创建"""
    service = FeishuViewSetupService()

    # Mock lark-cli 调用
    call_log: list[tuple[str, list[str]]] = []

    def mock_run(command, **kwargs):
        call_log.append((" ".join(command[:5]), command))
        # 根据命令返回不同结果
        cmd_str = " ".join(command)
        if "+view-create" in cmd_str:
            return SimpleNamespace(
                returncode=0,
                stdout='{"data":{"view":{"view_id":"view-new"}}}',
                stderr="",
            )
        # 其他命令（set-filter, set-sort, etc.）
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("app.services.feishu_view_setup.subprocess.run", mock_run)

    config = ViewConfig(
        name="测试视图",
        type="grid",
        filter_config={"logic": "and", "conditions": [["状态", "is", "synced"]]},
        sort_config={"sort_config": [{"field": "开始时间", "desc": False}]},
        visible_fields=["标题", "状态"],
    )
    existing_views: dict[str, str] = {}

    result = service.setup_view(config, existing_views)
    assert result.action == "created"
    assert result.view_id == "view-new"
    # 验证调用了 3 次 lark-cli（create + filter + sort + visible_fields）
    assert len(call_log) == 4


def test_setup_all_views_is_idempotent(monkeypatch) -> None:
    """批量设置是幂等的"""
    service = FeishuViewSetupService()

    # Mock lark-cli
    def mock_run(command, **kwargs):
        cmd_str = " ".join(command)
        if "+view-list" in cmd_str:
            # 返回已存在的视图
            return SimpleNamespace(
                returncode=0,
                stdout='{"data":{"views":[{"name":"活动总表","id":"v1"},{"name":"讲座","id":"v2"}]}}',
                stderr="",
            )
        if "+view-create" in cmd_str:
            return SimpleNamespace(
                returncode=0,
                stdout='{"data":{"view":{"view_id":"v-new"}}}',
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr("app.services.feishu_view_setup.subprocess.run", mock_run)

    # 只测试 3 个视图
    configs = [
        ViewConfig(name="活动总表", type="grid"),
        ViewConfig(name="讲座", type="grid"),
        ViewConfig(name="新视图", type="grid"),
    ]

    result = service.setup_all_views(configs)
    assert result.total == 3
    assert result.updated == 2  # 活动总表和讲座已存在，被更新
    assert result.created == 1  # 新视图被创建
    assert result.failed == 0


def test_setup_view_handles_lark_cli_error(monkeypatch) -> None:
    """lark-cli 失败时记录错误"""
    service = FeishuViewSetupService()

    def mock_run(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="permission denied")

    monkeypatch.setattr("app.services.feishu_view_setup.subprocess.run", mock_run)

    config = ViewConfig(name="失败视图", type="grid")
    result = service.setup_view(config, {})
    assert result.action == "failed"
    assert "permission denied" in result.error


def test_is_windows_cmd_launcher() -> None:
    """Windows .cmd 扩展名检测"""
    assert is_windows_cmd_launcher("lark-cli.cmd") is True
    assert is_windows_cmd_launcher("lark-cli") is False
    assert is_windows_cmd_launcher("/usr/bin/lark-cli") is False
