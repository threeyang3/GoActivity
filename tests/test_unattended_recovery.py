import sqlite3
from unittest.mock import Mock

from desktop.maintenance import backup_database
from desktop.service_controller import ServiceController
from app.services.automation_guard import AutomationGuardService


def test_online_backup_includes_uncheckpointed_wal(tmp_path):
    source = tmp_path / "live.db"
    with sqlite3.connect(source) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("CREATE TABLE items(value TEXT)")
        conn.execute("INSERT INTO items VALUES ('preserved')")
        conn.commit()
        snapshot = backup_database(source, tmp_path / "backups", "test")
        with sqlite3.connect(snapshot) as restored:
            assert restored.execute("SELECT value FROM items").fetchall() == [("preserved",)]
            assert restored.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_backup_retention_never_removes_unrelated_files(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE items(id INTEGER)")
    folder = tmp_path / "backups"
    folder.mkdir()
    unrelated = folder / "important.db"
    unrelated.write_bytes(b"keep")
    for _ in range(4):
        backup_database(source, folder, "test", keep=2)
    assert len(list(folder.glob("test-*.db"))) == 2
    assert unrelated.read_bytes() == b"keep"


def test_service_recovery_continues_after_multiple_failures(monkeypatch):
    manager = ServiceController()
    svc = manager.goactivity
    svc.restart_count = 20
    delays = []
    monkeypatch.setattr(svc._monitor_stop, "wait", lambda delay: delays.append(delay) or False)
    launch = Mock(side_effect=lambda **_: setattr(svc, "status", "running"))
    monkeypatch.setattr(manager, "start_goactivity", launch)
    assert manager._restart_with_backoff(svc)
    assert delays == [300]
    assert svc.restart_count == 21
    launch.assert_called_once_with(start_monitor=False)


def test_user_stop_cancels_retry(monkeypatch):
    manager = ServiceController()
    svc = manager.goactivity
    svc._monitor_stop.set()
    launch = Mock()
    monkeypatch.setattr(manager, "start_goactivity", launch)
    assert not manager._restart_with_backoff(svc)
    launch.assert_not_called()


def test_health_detects_blocked_but_reachable_collector(monkeypatch, db):
    from app.adapters.we_mp_rss import WeMpRssClient
    monkeypatch.setattr(WeMpRssClient, "collection_status", lambda _: {
        "cooldown": True, "authorized": False, "auth_remaining_seconds": 0,
        "last_success_at": None,
    })
    result = AutomationGuardService(db).collection_health()
    assert result["status"] == "degraded"
    assert len(result["issues"]) == 3


def test_old_publications_do_not_hide_broken_collection(db):
    from datetime import timedelta
    from app.models import Article
    from app.utils.time import utcnow
    db.add(Article(article_id="old-unattended", mp_name="Old source", publish_time="2020-01-01", created_at=utcnow() - timedelta(days=90)))
    db.commit()
    row = next(row for row in AutomationGuardService(db).account_health() if row["mp_name"] == "Old source")
    assert row["status"] == "stale"


def test_weekly_report_uses_unix_monday_not_tuesday():
    from datetime import datetime
    from app.utils.cron import parse_cron
    trigger = parse_cron("0 9 * * 1")
    monday = datetime(2026, 10, 12, 8, tzinfo=trigger.timezone)
    next_time = trigger.get_next_fire_time(None, monday)
    assert next_time.weekday() == 0
    assert next_time.day == 12 and next_time.hour == 9


def test_unix_sunday_and_weekday_ranges():
    from app.utils.cron import parse_cron
    assert str(parse_cron("0 9 * * 0").fields[4]) == "sun"
    assert str(parse_cron("0 9 * * 7").fields[4]) == "sun"
    assert str(parse_cron("0 9 * * 1-5").fields[4]) == "mon,tue,wed,thu,fri"


def test_hung_execution_requests_service_recovery():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from app.routes.health import _check_sync_execution
    auto = SimpleNamespace(get_sync_status=lambda: {"running": True, "started_at": (datetime.now(timezone.utc) - timedelta(hours=4)).isoformat()})
    assert _check_sync_execution(auto, SimpleNamespace(auto_sync_stale_minutes=180))["status"] == "error"


def test_invalid_backup_metadata_is_reported_not_crashed(tmp_path):
    from types import SimpleNamespace
    from app.services.backup_status import backup_status
    folder = tmp_path / "backups"
    folder.mkdir()
    (folder / "status.json").write_text('[]')
    assert backup_status(SimpleNamespace(storage_dir=tmp_path)) == {"status": "missing"}


def test_local_collector_avoids_ipv6_fallback():
    from app.config import Settings
    assert Settings(_env_file=None, we_mp_rss_base_url="http://localhost:8001").we_mp_rss_base_url == "http://127.0.0.1:8001"
    assert Settings(_env_file=None, we_mp_rss_base_url="https://remote.example:8001").we_mp_rss_base_url == "https://remote.example:8001"


def test_supervisor_recovers_crashes_and_respects_normal_exit(tmp_path):
    from types import SimpleNamespace
    from desktop.supervisor import supervise
    exits = iter([1, 1, 0])
    delays = []
    assert supervise(["gui"], tmp_path, run=lambda *_a, **_k: SimpleNamespace(returncode=next(exits)), wait=delays.append) == 0
    assert delays == [5, 10]
