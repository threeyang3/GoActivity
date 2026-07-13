from desktop.service_controller import ServiceController


def test_auto_restart_reuses_existing_monitor_thread(monkeypatch):
    controller = ServiceController()
    service = controller.goactivity
    calls = []
    monkeypatch.setattr("desktop.service_controller.time.sleep", lambda _: None)

    def start_goactivity(*, start_monitor=True):
        calls.append(start_monitor)
        service.status = "running"
        return True

    monkeypatch.setattr(controller, "start_goactivity", start_goactivity)

    assert controller._restart_with_backoff(service) is True
    assert calls == [False]
