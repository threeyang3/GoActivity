import io

from desktop.service_controller import ServiceController, check_health


def test_auto_restart_reuses_existing_monitor_thread(monkeypatch):
    controller = ServiceController()
    service = controller.goactivity
    calls = []
    monkeypatch.setattr("desktop.service_controller.time.sleep", lambda _: None)
    monkeypatch.setattr(service._monitor_stop, "wait", lambda _: False)

    def start_goactivity(*, start_monitor=True):
        calls.append(start_monitor)
        service.status = "running"
        return True

    monkeypatch.setattr(controller, "start_goactivity", start_goactivity)

    assert controller._restart_with_backoff(service) is True
    assert calls == [False]


def test_health_check_accepts_successful_html_endpoint(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(b"<!doctype html><title>WeRSS docs</title>"),
    )

    assert check_health("127.0.0.1", 8001, "/api/docs") == "ok"


def test_health_check_preserves_explicit_degraded_status(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: Response(b'{"status":"degraded"}'),
    )

    assert check_health("127.0.0.1", 8000) == "degraded"


def test_service_interpreters_honor_configured_paths(monkeypatch, tmp_path):
    from desktop.service_controller import find_goactivity_python, find_rss_python

    ga_python = tmp_path / "goactivity-python.exe"
    rss_python = tmp_path / "werss-python.exe"
    ga_python.touch()
    rss_python.touch()
    monkeypatch.setenv("GOACTIVITY_PYTHON", str(ga_python))
    monkeypatch.setenv("WEMP_RSS_PYTHON", str(rss_python))

    assert find_goactivity_python() == str(ga_python)
    assert find_rss_python() == str(rss_python)
