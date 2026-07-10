"""dashboard.py 路由测试。"""

from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_stats_returns_expected_keys() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/stats")

    assert response.status_code == 200
    body = response.json()
    assert "articles" in body
    assert "events" in body
    assert "latest_sync" in body
    assert "recent_events" in body
    assert "total" in body["articles"]
    assert "total" in body["events"]
    assert "active" in body["events"]
    assert "synced" in body["events"]
    assert "pending" in body["events"]
    assert "failed" in body["events"]
    assert "review" in body["events"]
    assert "failed_extract" in body["events"]
    assert "failed_sync" in body["events"]
    assert "needs_image_retry" in body["events"]


def test_dashboard_events_returns_paginated() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/events", params={"page": 1, "page_size": 10})

    assert response.status_code == 200
    body = response.json()
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert "pages" in body
    assert "items" in body
    assert isinstance(body["items"], list)


def test_dashboard_events_filter_by_status() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/events", params={"status": "synced"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)


def test_dashboard_events_filter_by_category() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/events", params={"category": "讲座"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)


def test_dashboard_events_filter_by_activity_kind() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/events", params={"activity_kind": "lecture"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)


def test_dashboard_events_filter_by_general_recruitment_kind() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/events", params={"activity_kind": "general_recruitment"})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)


def test_dashboard_sync_logs_returns_list() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/sync-logs", params={"limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


def test_dashboard_sync_runs_returns_list() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/sync-runs", params={"limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)


def test_dashboard_feishu_link_returns_config() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/feishu-link")

    assert response.status_code == 200
    body = response.json()
    assert "configured" in body
    assert "url" in body


def test_dashboard_history_exposes_month_alias() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/history")

    assert response.status_code == 200
    body = response.json()
    assert "months" in body
    assert "available_months" in body


def test_root_redirects_to_dashboard() -> None:
    with TestClient(app) as client, client as c:
        response = c.get("/", follow_redirects=False)

    assert response.status_code == 307  # redirect
