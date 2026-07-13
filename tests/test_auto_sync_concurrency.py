import threading

import pytest

from app.services.auto_sync import AutoSyncService


def test_manual_sync_allows_only_one_active_run(monkeypatch):
    service = AutoSyncService()
    started = threading.Event()
    release = threading.Event()

    def execute():
        started.set()
        release.wait(timeout=2)
        return {"articles_fetched": 0, "events_synced": 0, "events_failed": 0}

    monkeypatch.setattr(service, "_execute_sync", execute)

    first = service.run_now()
    assert started.wait(timeout=1)
    second = service.run_now()
    release.set()

    assert first["status"] == "started"
    assert second["status"] == "already_running"


def test_scheduled_sync_skips_when_manual_sync_is_reserved(monkeypatch):
    service = AutoSyncService()
    calls = []
    assert service._begin_run("manual") is True
    monkeypatch.setattr(service, "_execute_sync", lambda: calls.append("executed"))

    service._run_sync()

    assert calls == []
    service._execution_lock.release()


def test_manual_sync_releases_reservation_when_thread_start_fails(monkeypatch):
    service = AutoSyncService()

    class BrokenThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("thread unavailable")

    monkeypatch.setattr("app.services.auto_sync.threading.Thread", BrokenThread)

    with pytest.raises(RuntimeError, match="thread unavailable"):
        service.run_now()

    assert service._execution_lock.acquire(blocking=False) is True
    service._execution_lock.release()
