from types import SimpleNamespace

from app.db import SessionLocal, init_db
from app.models import Article, Event, SyncLog
from app.services.feishu import (
    FeishuCLIClient,
    FeishuOpenAPIClient,
    LarkCLIClient,
    _build_client,
    build_record_fields,
    checkbox,
    multi_select_texts,
    number,
    select_text,
    to_datetime_str,
    url_link,
)


def test_feishu_client_retries_until_success(monkeypatch) -> None:
    init_db()
    db = SessionLocal()
    event = Event(event_id="event_retry_test", article_id="article_retry_test", title="Retry test")
    db.add(event)
    db.commit()

    calls = {"count": 0}

    def fake_run(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            return SimpleNamespace(returncode=1, stdout="", stderr="temporary failure")
        return SimpleNamespace(returncode=0, stdout='{"record_id":"rec-123"}', stderr="")

    monkeypatch.setattr("app.services.feishu.subprocess.run", fake_run)
    monkeypatch.setattr("app.services.feishu.time.sleep", lambda _: None)

    client = FeishuCLIClient(db)
    settings = client.settings
    original_dry_run = settings.feishu_dry_run
    original_retries = settings.feishu_max_retries
    original_provider = settings.feishu_provider
    try:
        settings.feishu_dry_run = False
        settings.feishu_max_retries = 3
        settings.feishu_provider = "cli"
        result = client.upsert_event(event)
        logs = db.query(SyncLog).filter(SyncLog.target_id == event.event_id).all()
        assert result["return_code"] == 0
        assert result["record_id"] == "rec-123"
        assert calls["count"] == 3
        assert len(logs) == 3
    finally:
        settings.feishu_dry_run = original_dry_run
        settings.feishu_max_retries = original_retries
        settings.feishu_provider = original_provider
        db.query(SyncLog).filter(SyncLog.target_id == event.event_id).delete()
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.commit()
        db.close()


def test_build_client_prefers_openapi_when_configured() -> None:
    init_db()
    db = SessionLocal()
    settings = FeishuCLIClient(db).settings
    original_provider = settings.feishu_provider
    original_cli_path = settings.feishu_cli_path
    original_app_id = settings.feishu_app_id
    original_app_secret = settings.feishu_app_secret
    original_app_token = settings.feishu_bitable_app_token
    original_table_id = settings.feishu_bitable_table_id
    try:
        settings.feishu_provider = "auto"
        settings.feishu_cli_path = "feishu"
        settings.feishu_app_id = "cli_xxx"
        settings.feishu_app_secret = "secret_xxx"
        settings.feishu_bitable_app_token = "app_token_xxx"
        settings.feishu_bitable_table_id = "tbl_xxx"
        client = _build_client(db)
        assert isinstance(client, FeishuOpenAPIClient)
    finally:
        settings.feishu_provider = original_provider
        settings.feishu_cli_path = original_cli_path
        settings.feishu_app_id = original_app_id
        settings.feishu_app_secret = original_app_secret
        settings.feishu_bitable_app_token = original_app_token
        settings.feishu_bitable_table_id = original_table_id
        db.close()


def test_openapi_client_creates_record(monkeypatch) -> None:
    init_db()
    db = SessionLocal()
    event = Event(event_id="event_openapi_create", article_id="article_openapi_create", title="Create test")
    db.add(event)
    db.commit()

    request_calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    def fake_post(url, json, timeout):
        assert url.endswith("/open-apis/auth/v3/tenant_access_token/internal")
        assert json["app_id"] == "cli_xxx"
        assert json["app_secret"] == "secret_xxx"
        return FakeResponse({"code": 0, "tenant_access_token": "tenant-token", "expire": 7200})

    def fake_request(method, url, headers, json, timeout):
        request_calls.append((method, url, headers, json, timeout))
        return FakeResponse({"code": 0, "data": {"record": {"record_id": "rec-openapi-1"}}})

    monkeypatch.setattr("app.services.feishu.requests.post", fake_post)
    monkeypatch.setattr("app.services.feishu.requests.request", fake_request)

    client = FeishuOpenAPIClient(db)
    settings = client.settings
    original_values = (
        settings.feishu_provider,
        settings.feishu_dry_run,
        settings.feishu_app_id,
        settings.feishu_app_secret,
        settings.feishu_bitable_app_token,
        settings.feishu_bitable_table_id,
    )
    try:
        settings.feishu_provider = "openapi"
        settings.feishu_dry_run = False
        settings.feishu_app_id = "cli_xxx"
        settings.feishu_app_secret = "secret_xxx"
        settings.feishu_bitable_app_token = "app_token_xxx"
        settings.feishu_bitable_table_id = "tbl_xxx"
        result = client.upsert_event(event)
        logs = db.query(SyncLog).filter(SyncLog.target_id == event.event_id).all()
        assert result["return_code"] == 0
        assert result["record_id"] == "rec-openapi-1"
        assert request_calls[0][0] == "POST"
        assert request_calls[0][1].endswith("/open-apis/bitable/v1/apps/app_token_xxx/tables/tbl_xxx/records")
        assert request_calls[0][2]["Authorization"] == "Bearer tenant-token"
        assert logs[-1].return_code == 0
    finally:
        (
            settings.feishu_provider,
            settings.feishu_dry_run,
            settings.feishu_app_id,
            settings.feishu_app_secret,
            settings.feishu_bitable_app_token,
            settings.feishu_bitable_table_id,
        ) = original_values
        db.query(SyncLog).filter(SyncLog.target_id == event.event_id).delete()
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.commit()
        db.close()


def test_openapi_client_updates_record(monkeypatch) -> None:
    init_db()
    db = SessionLocal()
    event = Event(
        event_id="event_openapi_update",
        article_id="article_openapi_update",
        title="Update test",
        feishu_record_id="rec-existing",
    )
    db.add(event)
    db.commit()

    request_calls = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    monkeypatch.setattr(
        "app.services.feishu.requests.post",
        lambda *args, **kwargs: FakeResponse({"code": 0, "tenant_access_token": "tenant-token", "expire": 7200}),
    )

    def fake_request(method, url, headers, json, timeout):
        request_calls.append((method, url))
        return FakeResponse({"code": 0, "data": {"record": {"record_id": "rec-existing"}}})

    monkeypatch.setattr("app.services.feishu.requests.request", fake_request)

    client = FeishuOpenAPIClient(db)
    settings = client.settings
    original_values = (
        settings.feishu_provider,
        settings.feishu_dry_run,
        settings.feishu_app_id,
        settings.feishu_app_secret,
        settings.feishu_bitable_app_token,
        settings.feishu_bitable_table_id,
    )
    try:
        settings.feishu_provider = "openapi"
        settings.feishu_dry_run = False
        settings.feishu_app_id = "cli_xxx"
        settings.feishu_app_secret = "secret_xxx"
        settings.feishu_bitable_app_token = "app_token_xxx"
        settings.feishu_bitable_table_id = "tbl_xxx"
        result = client.upsert_event(event)
        assert result["record_id"] == "rec-existing"
        assert request_calls == [
            (
                "PUT",
                "https://open.feishu.cn/open-apis/bitable/v1/apps/app_token_xxx/tables/tbl_xxx/records/rec-existing",
            )
        ]
    finally:
        (
            settings.feishu_provider,
            settings.feishu_dry_run,
            settings.feishu_app_id,
            settings.feishu_app_secret,
            settings.feishu_bitable_app_token,
            settings.feishu_bitable_table_id,
        ) = original_values
        db.query(SyncLog).filter(SyncLog.target_id == event.event_id).delete()
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.commit()
        db.close()


def test_build_client_prefers_lark_cli_when_configured() -> None:
    init_db()
    db = SessionLocal()
    settings = FeishuCLIClient(db).settings
    original_values = (
        settings.feishu_provider,
        settings.feishu_cli_path,
        settings.feishu_cli_as,
        settings.feishu_bitable_app_token,
        settings.feishu_bitable_table_id,
    )
    try:
        settings.feishu_provider = "auto"
        settings.feishu_cli_path = "lark-cli"
        settings.feishu_cli_as = "user"
        settings.feishu_bitable_app_token = "base_token_xxx"
        settings.feishu_bitable_table_id = "tbl_xxx"
        client = _build_client(db)
        assert isinstance(client, LarkCLIClient)
    finally:
        (
            settings.feishu_provider,
            settings.feishu_cli_path,
            settings.feishu_cli_as,
            settings.feishu_bitable_app_token,
            settings.feishu_bitable_table_id,
        ) = original_values
        db.close()


def test_lark_cli_client_parses_record_id(monkeypatch) -> None:
    init_db()
    db = SessionLocal()
    event = Event(event_id="event_lark_cli_test", article_id="article_lark_cli_test", title="Lark CLI test")
    db.add(event)
    db.commit()

    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout='{"ok":true,"data":{"record":{"record_id_list":["rec-lark-123"]}}}',
            stderr="",
        )

    monkeypatch.setattr("app.services.feishu.subprocess.run", fake_run)

    client = LarkCLIClient(db)
    settings = client.settings
    original_values = (
        settings.feishu_provider,
        settings.feishu_cli_path,
        settings.feishu_cli_as,
        settings.feishu_bitable_app_token,
        settings.feishu_bitable_table_id,
        settings.feishu_dry_run,
    )
    try:
        settings.feishu_provider = "lark_cli"
        settings.feishu_cli_path = "lark-cli"
        settings.feishu_cli_as = "user"
        settings.feishu_bitable_app_token = "base_token_xxx"
        settings.feishu_bitable_table_id = "tbl_xxx"
        settings.feishu_dry_run = False
        result = client.upsert_event(event)
        logs = db.query(SyncLog).filter(SyncLog.target_id == event.event_id).all()
        assert result["return_code"] == 0
        assert result["record_id"] == "rec-lark-123"
        assert len(logs) == 1
        assert "lark-cli base +record-upsert" in logs[0].command
    finally:
        (
            settings.feishu_provider,
            settings.feishu_cli_path,
            settings.feishu_cli_as,
            settings.feishu_bitable_app_token,
            settings.feishu_bitable_table_id,
            settings.feishu_dry_run,
        ) = original_values
        db.query(SyncLog).filter(SyncLog.target_id == event.event_id).delete()
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.commit()
        db.close()


def test_lark_cli_client_uploads_poster_attachments(monkeypatch) -> None:
    init_db()
    db = SessionLocal()
    event = Event(
        event_id="event_lark_cli_attachment",
        article_id="article_lark_cli_attachment",
        title="Lark CLI attachment test",
        poster_images='["storage\\\\images\\\\3216330155-2247645707_3\\\\873f60cddec01273.jpg"]',
    )
    db.add(event)
    db.commit()

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if "+record-upsert" in command:
            return SimpleNamespace(
                returncode=0,
                stdout='{"ok":true,"data":{"record":{"record_id_list":["rec-lark-attach"]}}}',
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr="")

    monkeypatch.setattr("app.services.feishu.subprocess.run", fake_run)

    client = LarkCLIClient(db)
    settings = client.settings
    original_values = (
        settings.feishu_provider,
        settings.feishu_cli_path,
        settings.feishu_cli_as,
        settings.feishu_bitable_app_token,
        settings.feishu_bitable_table_id,
        settings.feishu_poster_attachment_field,
        settings.feishu_dry_run,
    )
    try:
        settings.feishu_provider = "lark_cli"
        settings.feishu_cli_path = "lark-cli"
        settings.feishu_cli_as = "user"
        settings.feishu_bitable_app_token = "base_token_xxx"
        settings.feishu_bitable_table_id = "tbl_xxx"
        settings.feishu_poster_attachment_field = "海报附件"
        settings.feishu_dry_run = False
        result = client.upsert_event(event)
        assert result["record_id"] == "rec-lark-attach"
        assert any("+record-upsert" in command for command in calls)
    finally:
        (
            settings.feishu_provider,
            settings.feishu_cli_path,
            settings.feishu_cli_as,
            settings.feishu_bitable_app_token,
            settings.feishu_bitable_table_id,
            settings.feishu_poster_attachment_field,
            settings.feishu_dry_run,
        ) = original_values
        db.query(SyncLog).filter(SyncLog.target_id == event.event_id).delete()
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.commit()
        db.close()


def test_build_record_fields_uses_typed_values() -> None:
    init_db()
    db = SessionLocal()
    article = Article(
        article_id="article_payload_activity_kind",
        title="毕业典礼志愿者招募",
        mp_name="北大团委",
        publish_time="2026-06-10 12:00:00",
    )
    event = Event(
        event_id="event_payload_activity_kind",
        article_id=article.article_id,
        title="毕业典礼志愿者招募",
        activity_kind="volunteer_recruitment",
        tags='["免费", "学生专属"]',
        start_time="2026-06-18 19:00:00",
        end_time="2026-06-18 21:00:00",
        location="北京大学百年讲堂",
        source_url="https://example.com/article/1",
        status="extracted",
        event_time_status="scheduled",
        retention_decision="keep",
        user_keep=False,
        confidence=0.87,
    )
    db.add(article)
    db.add(event)
    db.commit()

    settings = LarkCLIClient(db).settings
    original_values = (
        settings.feishu_activity_kind_field,
        settings.feishu_activity_kind_code_field,
    )
    try:
        settings.feishu_activity_kind_field = "活动类型"
        settings.feishu_activity_kind_code_field = "活动类型编码"
        payload = build_record_fields(event)
        # SingleSelect (字符串格式)
        assert payload["活动类型"] == "志愿者招募"
        # 旧编码列不再写入
        assert "活动类型编码" not in payload
        # MultiSelect (字符串列表格式)
        assert payload["标签"] == ["免费", "学生专属"]
        # DateTime -> 字符串格式
        assert payload["开始时间"] == "2026-06-18 19:00:00"
        assert payload["结束时间"] == "2026-06-18 21:00:00"
        # URL (字符串格式)
        assert payload["原文链接"] == "https://example.com/article/1"
        # Location (不写，因为需要经纬度)
        assert "地点" not in payload
        # SingleSelect (状态/时间状态/保留决策) - 字符串格式
        assert payload["状态"] == "extracted"
        assert payload["时间状态"] == "scheduled"
        assert payload["保留决策"] == "keep"
        # Number round 2 位
        assert payload["置信度"] == 0.87
        # Checkbox
        assert payload["用户置顶"] is False
        # Text 字段
        assert payload["标题"] == "毕业典礼志愿者招募"
        # 公众号从 Article join
        assert payload["公众号"] == "北大团委"
        # 关键回归：海报文本列不再写
        assert "海报" not in payload
    finally:
        (
            settings.feishu_activity_kind_field,
            settings.feishu_activity_kind_code_field,
        ) = original_values
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.query(Article).filter(Article.article_id == article.article_id).delete()
        db.commit()
        db.close()


def test_to_datetime_str_handles_various_formats() -> None:
    # 完整 datetime
    full = to_datetime_str("2026-06-18 19:00:00")
    assert full == "2026-06-18 19:00:00"
    # 仅日期 -> 当天 00:00:00
    day_only = to_datetime_str("2026-06-18")
    assert day_only == "2026-06-18 00:00:00"
    # 空 / None / 非法 -> None
    assert to_datetime_str("") is None
    assert to_datetime_str(None) is None
    assert to_datetime_str("not a date") is None


def test_select_text_skips_unknown_options() -> None:
    # 未知选项 -> None（被白名单过滤）
    assert select_text("一级分类", "未知分类") is None
    # 空值 -> None
    assert select_text("一级分类", "") is None
    assert select_text("一级分类", None) is None
    # 合法选项 -> 返回值
    assert select_text("一级分类", "讲座") == "讲座"


def test_multi_select_texts_filters_unknown() -> None:
    assert multi_select_texts("标签", ["免费", "学生专属"]) == ["免费", "学生专属"]
    assert multi_select_texts("标签", ["免费", "invalid"]) == ["免费"]
    assert multi_select_texts("标签", []) is None
    assert multi_select_texts("标签", None) is None


def test_url_link_promotes_http_only() -> None:
    # http(s) -> 返回 URL 字符串
    assert url_link("https://example.com/a") == "https://example.com/a"
    assert url_link("http://example.com/a") == "http://example.com/a"
    # 非 http(s) -> 返回原文本
    assert url_link("weixin://x") == "weixin://x"
    assert url_link("") is None
    assert url_link(None) is None


def test_checkbox_and_number_normalizers() -> None:
    assert checkbox(True) is True
    assert checkbox(False) is False
    assert checkbox(None) is None
    assert number(0.87123) == 0.87
    assert number(0) is None
    assert number(None) is None
    assert number(0.5) == 0.5


def test_build_record_fields_omits_poster_text_column() -> None:
    init_db()
    db = SessionLocal()
    event = Event(
        event_id="event_payload_no_poster_text",
        article_id="article_payload_no_poster_text",
        title="No poster text column",
        poster_images='["storage/images/x.jpg"]',
    )
    db.add(event)
    db.commit()
    try:
        payload = build_record_fields(event)
        assert "海报" not in payload
    finally:
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.commit()
        db.close()


def test_openapi_upsert_uses_typed_fields(monkeypatch) -> None:
    init_db()
    db = SessionLocal()
    event = Event(
        event_id="event_openapi_typed",
        article_id="article_openapi_typed",
        title="OpenAPI typed test",
        activity_kind="lecture",
        start_time="2026-06-18 19:00:00",
        tags='["免费"]',
        source_url="https://example.com/x",
        status="extracted",
        confidence=0.9,
    )
    db.add(event)
    db.commit()

    request_calls: list[tuple[str, str, dict, dict, float]] = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    monkeypatch.setattr(
        "app.services.feishu.requests.post",
        lambda *args, **kwargs: FakeResponse({"code": 0, "tenant_access_token": "t", "expire": 7200}),
    )

    def fake_request(method, url, headers, json, timeout):
        request_calls.append((method, url, headers, json, timeout))
        return FakeResponse({"code": 0, "data": {"record": {"record_id": "rec-typed"}}})

    monkeypatch.setattr("app.services.feishu.requests.request", fake_request)

    client = FeishuOpenAPIClient(db)
    settings = client.settings
    original_values = (
        settings.feishu_provider,
        settings.feishu_dry_run,
        settings.feishu_app_id,
        settings.feishu_app_secret,
        settings.feishu_bitable_app_token,
        settings.feishu_bitable_table_id,
    )
    try:
        settings.feishu_provider = "openapi"
        settings.feishu_dry_run = False
        settings.feishu_app_id = "cli_xxx"
        settings.feishu_app_secret = "secret_xxx"
        settings.feishu_bitable_app_token = "app_token_xxx"
        settings.feishu_bitable_table_id = "tbl_xxx"
        result = client.upsert_event(event)
        assert result["return_code"] == 0
        assert result["record_id"] == "rec-typed"
        assert len(request_calls) == 1
        body = request_calls[0][3]
        # body 是 {"fields": {...}}
        fields = body["fields"]
        assert fields["活动类型"] == "讲座"
        assert fields["开始时间"] == "2026-06-18 19:00:00"
        assert fields["标签"] == ["免费"]
        assert fields["原文链接"] == "https://example.com/x"
        assert fields["置信度"] == 0.9
        assert "海报" not in fields
    finally:
        (
            settings.feishu_provider,
            settings.feishu_dry_run,
            settings.feishu_app_id,
            settings.feishu_app_secret,
            settings.feishu_bitable_app_token,
            settings.feishu_bitable_table_id,
        ) = original_values
        db.query(SyncLog).filter(SyncLog.target_id == event.event_id).delete()
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.commit()
        db.close()
