import pytest

from desktop.paths import project_root
from desktop.service_controller import _find_python


def test_packaged_manager_finds_external_workspace(monkeypatch, tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app/main.py").touch()
    (tmp_path / "we-mp-rss").mkdir()
    (tmp_path / "we-mp-rss/main.py").touch()
    monkeypatch.delenv("GOACTIVITY_PROJECT_ROOT", raising=False)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(tmp_path / "dist/GoActivity/GoActivity.exe"))
    assert project_root() == tmp_path


def test_explicit_invalid_workspace_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("GOACTIVITY_PROJECT_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        project_root()


def test_packaged_manager_never_launches_itself_as_python(monkeypatch, tmp_path):
    monkeypatch.delenv("GOACTIVITY_TEST_PYTHON", raising=False)
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("desktop.service_controller.Path.is_file", lambda _: False)
    with pytest.raises(FileNotFoundError):
        _find_python("GOACTIVITY_TEST_PYTHON", tmp_path, "absent-test-env")
