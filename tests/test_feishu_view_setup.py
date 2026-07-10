from app.db import init_db
from app.services.feishu_view_setup import (
    FeishuViewSetupService,
    ViewConfig,
    VIEW_CONFIGS,
)
from app.utils.lark_cli import is_windows_cmd_launcher, resolve_lark_cli_run_js


def test_view_configs_cover_all_views() -> None:
    """视图配置覆盖 11 个面向使用场景的视图"""
    assert len(VIEW_CONFIGS) == 11
    names = [v.name for v in VIEW_CONFIGS]
    expected = [
        "全部活动", "今日执行", "演出与放映", "讲座论坛", "比赛征集",
        "招募报名", "用户置顶", "待人工处理", "来源巡检", "过期回看", "活动归档",
    ]
    assert names == expected


def test_view_configs_have_correct_types() -> None:
    """每个视图类型正确"""
    type_map = {v.name: v.type for v in VIEW_CONFIGS}
    assert type_map["待人工处理"] == "kanban"
    # 其余都是 grid
    for name in ["全部活动", "今日执行", "演出与放映", "讲座论坛", "比赛征集", "招募报名", "用户置顶", "来源巡检", "过期回看", "活动归档"]:
        assert type_map[name] == "grid", f"{name} should be grid"


def test_view_configs_have_filter_where_expected() -> None:
    """所有视图都有 filter_config"""
    for config in VIEW_CONFIGS:
        assert config.filter_config is not None, f"{config.name} should have filter"


def test_view_configs_have_sort_where_expected() -> None:
    """Grid 视图都有 sort_config（待人工处理看板除外）"""
    views_without_sort = {"待人工处理"}
    for config in VIEW_CONFIGS:
        if config.name in views_without_sort:
            assert config.sort_config is None, f"{config.name} should not have sort"
        else:
            assert config.sort_config is not None, f"{config.name} should have sort"


def test_kanban_view_has_group_config() -> None:
    """看板视图有 group_config"""
    kanban = next(v for v in VIEW_CONFIGS if v.name == "待人工处理")
    assert kanban.group_config is not None
    assert kanban.group_config["group_config"][0]["field"] == "状态"


def test_setup_view_updates_existing(monkeypatch) -> None:
    """已存在的视图会更新配置"""
    monkeypatch.setattr("app.services.feishu_view_setup.build_lark_cli_command", lambda cli_path: ["lark-cli"])
    service = FeishuViewSetupService()

    # Mock lark-cli
    def mock_run(command, **kwargs):
        return {"return_code": 0, "stdout": "{}", "stderr": "", "data": {}}

    monkeypatch.setattr("app.services.feishu_view_setup.run_cli_command", mock_run)

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
    monkeypatch.setattr("app.services.feishu_view_setup.build_lark_cli_command", lambda cli_path: ["lark-cli"])
    service = FeishuViewSetupService()

    # Mock lark-cli 调用
    call_log: list[tuple[str, list[str]]] = []

    def mock_run(command, **kwargs):
        call_log.append((" ".join(command[:5]), command))
        cmd_str = " ".join(command)
        if "+view-create" in cmd_str:
            return {
                "return_code": 0,
                "stdout": '{"data":{"view":{"view_id":"view-new"}}}',
                "stderr": "",
                "data": {"data": {"view": {"view_id": "view-new"}}},
            }
        return {"return_code": 0, "stdout": "{}", "stderr": "", "data": {}}

    monkeypatch.setattr("app.services.feishu_view_setup.run_cli_command", mock_run)

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
    monkeypatch.setattr("app.services.feishu_view_setup.build_lark_cli_command", lambda cli_path: ["lark-cli"])
    service = FeishuViewSetupService()

    # Mock lark-cli
    def mock_run(command, **kwargs):
        cmd_str = " ".join(command)
        if "+view-list" in cmd_str:
            return {
                "return_code": 0,
                "stdout": '{"data":{"views":[{"name":"活动总表","id":"v1"},{"name":"讲座","id":"v2"}]}}',
                "stderr": "",
                "data": {"data": {"views": [{"name": "活动总表", "id": "v1"}, {"name": "讲座", "id": "v2"}]}},
            }
        if "+view-create" in cmd_str:
            return {
                "return_code": 0,
                "stdout": '{"data":{"view":{"view_id":"v-new"}}}',
                "stderr": "",
                "data": {"data": {"view": {"view_id": "v-new"}}},
            }
        return {"return_code": 0, "stdout": "{}", "stderr": "", "data": {}}

    monkeypatch.setattr("app.services.feishu_view_setup.run_cli_command", mock_run)

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
    monkeypatch.setattr("app.services.feishu_view_setup.build_lark_cli_command", lambda cli_path: ["lark-cli"])
    service = FeishuViewSetupService()

    def mock_run(command, **kwargs):
        return {"return_code": 1, "stdout": "", "stderr": "permission denied", "data": None}

    monkeypatch.setattr("app.services.feishu_view_setup.run_cli_command", mock_run)

    config = ViewConfig(name="失败视图", type="grid")
    result = service.setup_view(config, {})
    assert result.action == "failed"
    assert "permission denied" in result.error


def test_is_windows_cmd_launcher() -> None:
    """Windows .cmd 扩展名检测"""
    assert is_windows_cmd_launcher("lark-cli.cmd") is True
    assert is_windows_cmd_launcher("lark-cli") is False
    assert is_windows_cmd_launcher("/usr/bin/lark-cli") is False
