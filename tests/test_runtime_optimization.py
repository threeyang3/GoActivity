import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.auto_sync import AutoSyncService
from app.services.providers import RapidOCRProvider
from app.services.bot_consumer import BotEventConsumer
from app.services.automation_guard import AutomationGuardService
from desktop import service_controller as controller


def test_ocr_lazy_shared_and_serialized(monkeypatch):
    stats = {"created": 0, "active": 0, "peak": 0}
    lock = threading.Lock()

    class Engine:
        def __init__(self, **kwargs):
            assert kwargs == {"intra_op_num_threads": 1, "inter_op_num_threads": 1}
            stats["created"] += 1

        def __call__(self, path):
            with lock:
                stats["active"] += 1
                stats["peak"] = max(stats["peak"], stats["active"])
            time.sleep(0.01)
            with lock:
                stats["active"] -= 1
            return [[[], path, 1]], None

    monkeypatch.setattr(RapidOCRProvider, "_engine", None)
    monkeypatch.setitem(sys.modules, "rapidocr_onnxruntime", SimpleNamespace(RapidOCR=Engine))
    assert RapidOCRProvider().extract([]) == ""
    assert stats["created"] == 0
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda n: RapidOCRProvider().extract([str(n)]), range(5)))
    assert results == [str(n) for n in range(5)]
    assert stats["created"] == stats["peak"] == 1


def test_desktop_launches_direct_uvicorn(monkeypatch, tmp_path):
    manager = controller.ServiceController()
    manager.goactivity.log_path = str(tmp_path / "service.log")
    launch = Mock(return_value=Mock(pid=123))
    monkeypatch.setattr(controller, "check_port", lambda *_: False)
    monkeypatch.setattr(controller, "find_goactivity_python", lambda: "dedicated-python")
    monkeypatch.setattr(controller.subprocess, "Popen", launch)
    monkeypatch.setattr(manager, "_wait_health", lambda *_: True)
    monkeypatch.delenv("OPENBLAS_NUM_THREADS", raising=False)
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    assert manager.start_goactivity(start_monitor=False)
    args, kwargs = launch.call_args
    assert args[0][:4] == ["dedicated-python", "-m", "uvicorn", "app.main:app"]
    assert kwargs["cwd"] == str(controller.PROJECT_ROOT)
    assert kwargs["env"]["OPENBLAS_NUM_THREADS"] == "1"
    assert kwargs["env"]["OMP_NUM_THREADS"] == "2"
    manager.goactivity._log_handle.close()


def test_windows_stop_includes_children(monkeypatch):
    manager = controller.ServiceController()
    manager.goactivity.running = True
    manager.goactivity.process = Mock(pid=123)
    stop = Mock()
    monkeypatch.setattr(controller.sys, "platform", "win32")
    monkeypatch.setattr(controller.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(controller.subprocess, "run", stop)
    manager.stop_goactivity()
    assert stop.call_args.args[0] == ["taskkill", "/PID", "123", "/T", "/F"]
    assert manager.goactivity.process is None


def test_dry_spell_does_not_trigger_during_cooldown(monkeypatch, db):
    client = Mock()
    client.collection_status.return_value = {"cooldown": True}
    monkeypatch.setattr("app.adapters.we_mp_rss.WeMpRssClient", lambda: client)
    assert AutoSyncService()._trigger_we_mp_rss_collection(db) == []
    client.list_message_tasks.assert_not_called()


def test_dry_spell_stops_waiting_when_queue_finishes(monkeypatch, db):
    client = Mock()
    client.collection_status.return_value = {"cooldown": False, "queue_pending": 0, "active_count": 0, "pending_count": 0}
    client.list_message_tasks.return_value = [{"id": "test", "name": "test"}]
    client.trigger_message_task.return_value = {"count": 1}
    articles = Mock()
    articles.fetch_candidates.return_value = []
    monkeypatch.setattr("app.adapters.we_mp_rss.WeMpRssClient", lambda: client)
    monkeypatch.setattr("app.services.auto_sync.ArticleService", lambda _: articles)
    monkeypatch.setattr("app.services.auto_sync._time.sleep", lambda _: None)
    assert AutoSyncService()._trigger_we_mp_rss_collection(db) == []
    articles.fetch_candidates.assert_called_once()


def test_priority_collection_counts_business_rejections(monkeypatch, db):
    service = AutomationGuardService(db)
    service.settings = SimpleNamespace(priority_accounts="")
    monkeypatch.setattr(service, "_mps_url", lambda: "http://test/mps")
    monkeypatch.setattr(service, "_list_remote_accounts", lambda: [{"id": "a", "mp_name": "a"}, {"id": "b", "mp_name": "b"}])
    monkeypatch.setattr(service, "_rss_headers", lambda: {})
    responses = iter([SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"code": 42901}),
                      SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"code": 50001})])
    monkeypatch.setattr("app.services.automation_guard.requests.get", lambda *a, **k: next(responses))
    result = service.trigger_priority_collection()
    assert result["triggered"] == []
    assert result["skipped"] == ["a"]
    assert result["failed"][0]["mp_name"] == "b"


def test_bot_shutdown_includes_cli_descendants(monkeypatch):
    process = Mock(pid=456)
    process.poll.return_value = None
    stop = Mock()
    monkeypatch.setattr("app.services.bot_consumer.sys.platform", "win32")
    monkeypatch.setattr("app.services.bot_consumer.subprocess.run", stop)
    BotEventConsumer._stop_process(process)
    assert stop.call_args.args[0] == ["taskkill", "/PID", "456", "/T", "/F"]


def test_bot_repeated_immediate_exit_is_bounded(monkeypatch):
    consumer = BotEventConsumer()
    launches = []
    def fail():
        launches.append(1)
        from app.exceptions import ProviderError
        raise ProviderError("test")
    monkeypatch.setattr(consumer, "_run_consumer", fail)
    monkeypatch.setattr(consumer._stop_event, "wait", lambda _: False)
    consumer._consume_loop()
    assert len(launches) == consumer._max_restarts
